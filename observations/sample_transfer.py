"""Natural-key transfer of video samples; never transfers credentials or grants roles."""
import uuid
from decimal import Decimal, InvalidOperation
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import Sample, Species, Country, Region, Site, DiveTrip, youtube_id


# Fields added after the first transfer format: older rows lack them (defaulted to '').
TAXONOMY_FIELDS = ('order', 'family', 'genus', 'identification_qualifier', 'life_stage')
# The observation note, added later still: an older row without it leaves the target's note as it is.
NOTE_FIELDS = ('note_he', 'note_en')


def _describe(sample):
    """Short, identifying text for a Sample in an error message -- an operator resolving a
    transfer conflict in admin needs to know exactly which record(s) to open, not just that
    a conflict exists."""
    identity = sample.title or sample.taxon_name or 'ללא כותרת'
    return f'#{sample.pk} ({identity}, מסע {sample.trip_id})'


def sample_row(obj, fields, include_deleted=False):
    """The transferable row of a sample. `include_deleted` (the table export) marks a soft-deleted sample with
    'deleted': '1' -- an extra key beside `fields` that the importer takes out first (see sample_plan)."""
    result = {}
    for field in fields:
        if field == 'trip':
            result[field] = obj.trip.code if obj.trip_id else None
            continue
        if field == 'gallery_source':
            # travels as the owning sample's fixed transfer id ('' for none), never its numeric id
            result[field] = str(obj.gallery_source.transfer_id) if obj.gallery_source_id and obj.gallery_source else ''
            continue
        value = getattr(obj, field)
        if field in ('transfer_id','image'): value = str(value)
        elif field == 'owner': value = value.get_username()
        elif field == 'species': value = value.scientific_name if value else None
        elif field == 'site': value = {'name': value.name, 'region': value.region.name, 'country': value.region.country.name} if value else None
        elif field == 'depth': value = str(value) if value is not None else None
        result[field] = value
    if include_deleted and obj.deleted_at: result['deleted'] = '1'
    return result


def _file_species_keys(document):
    """transfer id -> (trip code, species, variant) of every live species row in the file, or None for a row
    that deletes its observation -- what each observation in the file will be once the import is done."""
    keys = {}
    for row in document.get('rows', []):
        if not isinstance(row, dict) or not isinstance(row.get('transfer_id'), str): continue
        try: tid = str(uuid.UUID(row['transfer_id']))
        except ValueError: continue
        if row.get('deleted') in ('1', 1, True): keys[tid] = None
        elif row.get('kind') == 'species' and row.get('species'):
            keys[tid] = (row.get('trip'), row.get('species'), (row.get('undetermined_variant') or '').strip())
        else: keys[tid] = ('', '', '')
    return keys


def _same_species_on_trip(values, exclude):
    """The live species observation already here for this row's trip + species + variant (one trip records a
    species once -- see Sample.clean), other than `exclude`."""
    from .table_transfer import unique
    if values.get('kind') != 'species' or not isinstance(values.get('species'), str) or not isinstance(values.get('trip'), DiveTrip):
        return None
    species = unique(Species, scientific_name=values['species'])
    if species is None: return None
    query = Sample.objects.filter(kind=Sample.Kind.SPECIES, species=species, trip=values['trip'], deleted_at__isnull=True,
                                  undetermined_variant=(values.get('undetermined_variant') or '').strip())
    if exclude is not None: query = query.exclude(pk=exclude.pk)
    return query.order_by('pk').first()


def _natural_key(kind, trip, species, variant, title, taxon):
    """What an observation is, independent of its transfer id: a species on a trip (a trip records a species
    once), a dive-trip collection by its title, an order/family/genus observation by its taxon. None when that
    is not enough to tell it apart."""
    if not trip: return None
    if kind == 'species': return ('species', trip, species, (variant or '').strip()) if species else None
    if kind == 'collection': return ('collection', trip, title.strip()) if (title or '').strip() else None
    if kind in ('order', 'family', 'genus'): return (kind, trip, taxon.strip()) if (taxon or '').strip() else None
    return None


def _row_key(row):
    kind = row.get('kind')
    return _natural_key(kind, row.get('trip'), row.get('species'), row.get('undetermined_variant'),
                        row.get('title') or '', row.get(kind) if kind in ('order', 'family', 'genus') else '')


def _sample_key(sample):
    return _natural_key(sample.kind, sample.trip.code if sample.trip_id else None,
                        sample.species.scientific_name if sample.species_id else None, sample.undetermined_variant,
                        sample.title or '', getattr(sample, sample.kind, '') if sample.kind in ('order', 'family', 'genus') else '')


def crossed_transfer_ids(document):
    """{file transfer id: the live observation here it really is} for rows whose transfer id belongs here to a
    DIFFERENT observation. Two observations that share one photo (a species observation and the dive-trip
    collection made from it) can end up here with each other's transfer id, or with an id the source never had.
    A row whose id names an observation of another kind is matched by what it is instead: the one live
    observation here with the row's natural key (see _natural_key) whose own id is not in the file.
    The observation that held the id is then free, and a row of the file with no match here that is exactly that
    observation is matched to it. The matched observations take the file's transfer ids (see free_transfer_ids)."""
    rows = {}
    for row in document.get('rows', []):
        if not isinstance(row, dict) or row.get('deleted') in ('1', 1, True) or not isinstance(row.get('transfer_id'), str): continue
        try: rows[str(uuid.UUID(row['transfer_id']))] = row
        except ValueError: continue
    if not rows: return {}
    live = Sample.objects.filter(deleted_at__isnull=True).select_related('trip', 'species')
    holders = {str(s.transfer_id): s for s in live.filter(transfer_id__in=list(rows))}
    by_key = {}
    for tid, row in rows.items():
        holder = holders.get(tid)
        key = _row_key(row)
        # only an id held by another KIND of observation (a collection holding a species observation's id, or the
        # reverse): a species observation changing its species keeps its id (see the same-species check in sample_plan)
        if holder is None or key is None or holder.kind == row.get('kind'): continue
        by_key.setdefault(key, []).append(tid)
    if not by_key: return {}
    trips = {key[1] for key in by_key}
    candidates = {}
    for sample in live.filter(trip__code__in=trips):
        candidates.setdefault(_sample_key(sample), []).append(sample)
    result = {}; released = []
    for key, tids in by_key.items():
        found = [s for s in candidates.get(key, []) if str(s.transfer_id) not in rows]
        if len(tids) != 1 or len(found) != 1: continue
        result[tids[0]] = found[0]; released.append(holders[tids[0]])
    taken = {s.pk for s in result.values()}
    for holder in released:
        if holder.pk in taken: continue
        key = _sample_key(holder)
        matches = [tid for tid, row in rows.items() if tid not in holders and tid not in result and _row_key(row) == key]
        if len(matches) == 1: result[matches[0]] = holder; taken.add(holder.pk)
    return result


def free_transfer_ids(samples):
    """Before saving observations that take a transfer id another observation here still holds (see
    crossed_transfer_ids), park the holders on fresh ids -- each takes its own final id when it is saved."""
    for sample in samples:
        if getattr(sample, '_retid', False):
            Sample.objects.filter(transfer_id=sample.transfer_id).exclude(pk=sample.pk).update(transfer_id=uuid.uuid4())


def sample_plan(document, fields, restore_deleted=True):
    """`restore_deleted`: a live row whose observation is deleted here restores it (a table transfer: the source is the
    truth about deletions). The image manager's uploads pass False and skip such a row instead."""
    from .table_transfer import unique
    result = []; seen = set(); targets = set()
    file_keys = _file_species_keys(document)
    crossed = crossed_transfer_ids(document)
    for incoming in document['rows']:
        # A deleted observation travels as its normal row plus 'deleted': '1' (an older environment that does not know
        # the key rejects such a file, like any other format change). It only ever deletes: see below.
        deleted = False
        if isinstance(incoming, dict) and 'deleted' in incoming:
            incoming = dict(incoming); deleted = incoming.pop('deleted') in ('1', 1, True)
        missing = set(fields) - set(incoming) if isinstance(incoming, dict) else None
        keep_notes = bool(missing) and set(NOTE_FIELDS) <= missing
        if missing and set(incoming) <= set(fields) and missing - set(TAXONOMY_FIELDS) - {'gallery_source', 'title_en'} - set(NOTE_FIELDS) in (set(), {'transfer_id','image'}):
            # A row from an older environment/file: no order/family/genus/qualifier/life stage
            # (a taxon-level sample then carried its name in species_other), and possibly no
            # transfer_id/image either (the oldest EXIF rows).
            import uuid
            incoming = dict(incoming)
            if 'transfer_id' not in incoming:
                incoming = dict(incoming, transfer_id=str(uuid.uuid5(uuid.NAMESPACE_URL,incoming.get('video_url',''))), image='')
            for field in TAXONOMY_FIELDS: incoming.setdefault(field, '')
            if 'gallery_source' in fields: incoming.setdefault('gallery_source', '')
            if 'title_en' in fields: incoming.setdefault('title_en', '')
            for field in NOTE_FIELDS:
                if field in fields: incoming.setdefault(field, '')
            legacy_field = {'order': 'order', 'family': 'family', 'genus': 'genus'}.get(incoming.get('kind'))
            if legacy_field and not incoming[legacy_field] and isinstance(incoming.get('species_other'), str):
                incoming[legacy_field] = incoming['species_other']; incoming['species_other'] = ''
        if not isinstance(incoming, dict) or set(incoming) != set(fields):
            raise ValidationError('שדות Samples אינם תואמים. יש לעדכן קוד בשתי הסביבות.')
        values = dict(incoming)
        for field in fields:
            if field not in ('day','depth','gallery_order','species','site','trip','source_metadata') and not isinstance(values[field], str):
                raise ValidationError('ערך טקסט לא תקין: ' + field)
        if not isinstance(values['source_metadata'], dict): raise ValidationError('מידע מקור לא תקין.')
        if deleted:
            # Only the identity matters for a deleted observation: the one with this transfer id here is deleted too
            # (its media is removed with it, as the deletion did at the source); an observation that does not exist
            # here, or is already deleted, needs nothing -- it is never created just to be deleted.
            import uuid
            try: identity = str(uuid.UUID(values['transfer_id']))
            except (ValueError, TypeError): raise ValidationError('מזהה תצפית לא תקין.')
            if identity in seen: raise ValidationError('תצפית כפולה בקובץ.')
            seen.add(identity)
            target = unique(Sample, transfer_id=identity)
            if target is not None and not target.deleted_at:
                if target.pk in targets: raise ValidationError(f'כמה רשומות בקובץ המועבר מצביעות על אותו יעד: {_describe(target)}. יש לבדוק את הקובץ המועבר.')
                targets.add(target.pk)
                result.append({'object': target, 'label': _describe(target), 'action': 'soft_delete', 'warnings': [],
                               'changes': [{'field': 'מחיקה', 'before': 'פעילה', 'after': 'מחוקה (כולל המדיה)'}]})
            continue
        if values['trip'] is not None:
            if not isinstance(values['trip'],str): raise ValidationError('קוד מסע לא תקין.')
            values['trip'] = unique(DiveTrip, code=values['trip'])
            if values['trip'] is None: raise ValidationError('מסע חסר ביעד. יש להעביר מסעות לפני Samples.')
        import uuid
        try: identity = str(uuid.UUID(values['transfer_id']))
        except (ValueError, TypeError): raise ValidationError('מזהה תצפית לא תקין.')
        if identity in seen: raise ValidationError('תצפית כפולה בקובץ.')
        seen.add(identity)
        obj = crossed[identity] if identity in crossed else unique(Sample, transfer_id=identity)
        video = youtube_id(values['video_url']) if values['video_url'] else None
        # Deleted samples are excluded here on purpose: a soft-deleted sample and a later,
        # active replacement can legitimately share one video (the photographer re-entered
        # the observation under a new Sample after the old one was deleted) -- only the
        # still-active one should ever be treated as a match for an incoming row.
        candidates = [x for x in Sample.objects.exclude(video_url='').filter(deleted_at__isnull=True) if video and youtube_id(x.video_url) == video]
        if len(candidates)>1:
            details = '; '.join(_describe(c) for c in candidates)
            raise ValidationError(f'לסרטון {video} כמה תצפיות ביעד: {details}. יש למזג או למחוק את הכפולות בניהול לפני ההעברה.')
        if obj and obj.deleted_at and candidates:
            # The transfer_id match itself is the now-superseded, deleted sample (it was
            # transferred once before, kept its transfer_id, and has since been deleted
            # locally in favour of a fresh active sample for the same video) -- the live
            # candidate is the real target, not an unresolved conflict with it.
            obj = candidates[0]
        elif obj and candidates and obj.pk != candidates[0].pk:
            raise ValidationError(f'מזהה התצפית מצביע על {_describe(obj)}, אך הסרטון {video} מצביע על {_describe(candidates[0])} ביעד. יש לבדוק ולתקן את ההתאמה בניהול לפני ההעברה.')
        else:
            obj = obj or (candidates[0] if candidates else None)
        # One trip records a species once. The observation already here for this row's trip + species is the same
        # observation even when it carries another transfer id (e.g. it was re-entered here after the one with this
        # id was deleted): a row whose observation here is deleted updates that live one instead of failing. When the
        # row's own observation would become a second one, the import is blocked with both named -- unless the file
        # itself moves the other observation away (a species swap between two rows), which leaves no duplicate behind.
        # A brand-new row is left alone, as Sample.clean() leaves a new observation alone.
        allow_collision = False
        same = _same_species_on_trip(values, obj if obj and not obj.deleted_at else None) if obj else None
        if same is not None:
            row_text = f'{values["species"]}, מסע {values["trip"].code}, מזהה {identity}'
            same_tid = str(same.transfer_id)
            in_file = same_tid in file_keys and same_tid != identity
            moves_away = in_file and file_keys[same_tid] != (values['trip'].code, values['species'], (values.get('undetermined_variant') or '').strip())
            if moves_away:
                allow_collision = True
            elif not in_file and obj.deleted_at and same.pk not in targets:
                obj = same
            elif not moves_away:
                target_text = f' מתאימה ביעד ל-{_describe(obj)} (מזהה {obj.transfer_id}), אך' if not obj.deleted_at else ''
                raise ValidationError(f'השורה בקובץ ({row_text}){target_text} ביעד כבר קיימת תצפית לאותו מין באותו מסע: '
                                      f'{_describe(same)} (מזהה {same_tid}). יש למחוק או לתקן אחת מהן בניהול ביעד, ואז לייבא שוב.')
        if obj and obj.pk in targets:
            raise ValidationError(f'כמה רשומות בקובץ המועבר מצביעות על אותו יעד: {_describe(obj)}. יש לבדוק את הקובץ המועבר.')
        if obj: targets.add(obj.pk)
        # A live row whose observation is deleted here: it was restored at the source (deleted observations are transferred
        # too, so a live row is the source's current state) -- the preview lists the restoration and the row's values replace
        # the old ones. (Matching is by transfer id, or through a live observation with the same video, see above.)
        restoring = bool(obj and obj.deleted_at)
        if restoring and not restore_deleted:
            result.append({'object':None,'label':_describe(obj),'action':'skipped','changes':[],
                           'reason':f'התצפית ביעד ({_describe(obj)}) מסומנת כמחוקה. אם יש להחזיר אותה יש לעשות זאת בניהול ואז לייבא שוב; אחרת השורה הזו לא תועבר.'})
            continue
        retid = identity in crossed and obj is crossed[identity]
        if obj and not retid: values['transfer_id'] = str(obj.transfer_id)
        if keep_notes and obj:
            for field in NOTE_FIELDS: values[field] = getattr(obj, field)
        warnings = []; pending_gallery = None
        gallery_tid = values.pop('gallery_source', '') if 'gallery_source' in values else ''
        values['gallery_source'] = None
        if document.get('media_mode')=='separate':
            # A plain table transfer copies which photo each observation shows: its own alternate
            # image by file name, or its gallery image as the owning sample's transfer id. The
            # files themselves still travel through image management -- a file missing here is
            # copied anyway and reported, and the image comparison then lists it as missing.
            from django.core.files.storage import default_storage
            if gallery_tid:
                try: gallery_tid = str(uuid.UUID(gallery_tid))
                except (ValueError, TypeError): raise ValidationError('מזהה תמונה קיימת בגלריה לא תקין.')
                source = crossed[gallery_tid] if gallery_tid in crossed else Sample.objects.filter(transfer_id=gallery_tid, deleted_at__isnull=True).first()
                if source and source.gallery_source_id: source = source.gallery_source
                if source:
                    values['gallery_source'] = source; values['image'] = source.image.name if source.image else ''
                    if not source.image: warnings.append(f'לתצפית שהתמונה שלה נבחרה כתמונה קיימת בגלריה ({_describe(source)}) אין תמונה ביעד.')
                elif any(isinstance(r, dict) and r.get('transfer_id') == gallery_tid for r in document['rows']):
                    pending_gallery = gallery_tid; values['image'] = ''   # linked once that sample is saved too (apply)
                else:
                    values['image'] = ''
                    warnings.append('התמונה הקיימת בגלריה שייכת לתצפית שאינה קיימת ביעד ולא הועברה איתה; יש להעביר גם אותה ולייבא שוב.')
            elif values['image']:
                from .media_transfer import validate_image_name
                validate_image_name(values['image'])
                if not default_storage.exists(values['image']):
                    warnings.append(f'קובץ התמונה {values["image"]} חסר ביעד — שם התמונה הועתק; יש להעביר את הקובץ דרך ניהול התמונות.')
            # An order / family / genus observation may legitimately have no media of its own (its
            # page then borrows a species photo), so only the other kinds need one to be transferred.
            if not values['video_url'] and not values['image'] and not pending_gallery and values['kind'] not in ('order', 'family', 'genus'):
                result.append({'object':None,'label':values['title'] or incoming.get('species') or identity,
                               'action':'skipped','changes':[],
                               'reason':'התצפית לא הועברה: חסרה תמונה ביעד ואין סרטון. העבירו את התמונה דרך ניהול התמונות ואז ייבאו שוב.'})
                continue
        elif values['image']:
            # The image manager's own transfer flow (not plain table transfer): the doc's
            # rows carry a freshly content-hashed image name that will be written by this
            # same request, listed in _media_names.
            from .media_transfer import validate_image_name
            validate_image_name(values['image'])
            if values['image'] not in document.get('_media_names', []):
                from django.core.files.storage import default_storage
                if not default_storage.exists(values['image']): raise ValidationError('קובץ תמונה חסר; יש להעביר דרך ניהול התמונות.')
        values['owner'] = unique(get_user_model(), username=values['owner'])
        if values['owner'] is None: raise ValidationError('משתמש חסר ביעד: ' + incoming['owner'] + '. יש ליצור אותו או להתאים שם משתמש לפני ההעברה.')
        for field in ('species','site'):
            value = values[field]
            if value is None: continue
            if field == 'species':
                if not isinstance(value, str): raise ValidationError('שם מין לא תקין.')
                values[field] = unique(Species, scientific_name=value)
            else:
                if not isinstance(value, dict) or set(value) != {'name','region','country'} or not all(isinstance(v,str) for v in value.values()): raise ValidationError('מפתח אתר לא תקין.')
                values[field] = unique(Site, name=value['name'], region__name=value['region'], region__country__name=value['country'])
            if values[field] is None:
                # Name the actual missing value (not just "some reference-table value is
                # missing") -- this is the one thing an operator receiving files/rows from
                # another environment (image manager uploads, or a plain samples-table
                # transfer, both of which land here) needs to act on: add that species to
                # the target's species table first, or fix a typo, before transferring again.
                if field == 'species': raise ValidationError(f'המין "{value}" אינו קיים בטבלת המינים ביעד. יש להוסיף אותו קודם (או להעביר את טבלת המינים), או לתקן את שם המין, ואז לייבא שוב.')
                raise ValidationError(f'האתר "{value["name"]}" ({value["region"]}, {value["country"]}) אינו קיים בטבלת האתרים ביעד. יש להוסיף אותו קודם (או להעביר את טבלת האתרים), או לתקן את הנתונים, ואז לייבא שוב.')
        for field in ('day','gallery_order'):
            if values[field] is not None and type(values[field]) is not int: raise ValidationError('נדרש מספר שלם: '+field)
        try: values['depth'] = Decimal(str(values['depth'])) if values['depth'] is not None else None
        except InvalidOperation: raise ValidationError('עומק לא תקין.')
        if values['status'] not in ('pending','published'): raise ValidationError('מצב פרסום לא תקין.')
        candidate = Sample(**values)
        candidate._image_shared_with = document.get('_shared_image_tids', {}).get(values.get('image') or '', ())
        if allow_collision: candidate._allow_species_collision = True
        if obj:
            candidate.pk = obj.pk; candidate._state.adding = False
            for field in ('created_at','approved_by_id','approved_at'):
                setattr(candidate,field,getattr(obj,field))
        # a transfer id still held here by the observation it is being taken from (see free_transfer_ids)
        try: candidate.full_clean(exclude=['transfer_id'] if retid else None)
        except ValidationError as exc:
            # Incomplete legacy drafts may transfer, but cannot become public.
            errors = dict(exc.message_dict)
            if candidate.status == 'pending':
                for field in ('species','trip','order','family','genus'):
                    errors.pop(field, None)
            if errors: raise ValidationError(errors)
        other = candidate.species_other or candidate.site_other
        if candidate.status == 'published' and other:
            raise ValidationError('אין לפרסם רשומה עם ערכי אחר.')
        before = sample_row(obj, fields) if obj else {}
        after = sample_row(candidate, fields)
        if pending_gallery and 'gallery_source' in after: after['gallery_source'] = pending_gallery
        changes = [{'field':str(Sample._meta.get_field(f).verbose_name),'before':before.get(f,''),'after':after[f]} for f in fields if before.get(f) != after[f]]
        if restoring: changes.insert(0, {'field': 'שחזור', 'before': 'מחוקה', 'after': 'פעילה'})
        candidate._pending_gallery = pending_gallery
        if retid: candidate._retid = True
        result.append({'object':candidate,'label':candidate.title or str(candidate),'action':'new' if obj is None else 'update' if changes else 'same',
                       'changes':changes,'warnings':warnings})
    if document.get('purge_missing'):
        # Clean-up of the database: a DELETED observation here that the file does not mention at all (neither live nor
        # deleted) is removed for good. A live observation is never touched, whatever the file says.
        if not seen: raise ValidationError('לא ניתן למחוק סופית לפי קובץ ריק; הפעולה עלולה למחוק את כל התצפיות המחוקות.')
        for old in Sample.objects.filter(deleted_at__isnull=False).exclude(transfer_id__in=seen).order_by('pk'):
            result.append({'object': old, 'label': _describe(old), 'action': 'purge', 'warnings': [],
                           'changes': [{'field': 'מחיקה סופית', 'before': 'מחוקה (ניתנת לשחזור)', 'after': 'הסרה מהמסד — התצפית אינה בקובץ'}]})
    return result
