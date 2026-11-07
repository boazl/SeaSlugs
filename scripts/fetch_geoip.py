"""Downloads the free DB-IP "IP to Country Lite" database (CC BY 4.0, https://db-ip.com) to geoip/country.mmdb, for
the visit counter's countries (observations/geo.py). Run by build.sh on every deploy, so the database stays current.
Tries this month's edition, then last month's; on any failure it keeps an existing file and exits 0 -- a missing
database only makes the countries unknown, it must never fail a deploy."""
import datetime
import gzip
import shutil
import sys
import urllib.request
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / 'geoip' / 'country.mmdb'
URL = 'https://download.db-ip.com/free/dbip-country-lite-{:%Y-%m}.mmdb.gz'


def editions(today=None):
    today = today or datetime.date.today()
    last_month = today.replace(day=1) - datetime.timedelta(days=1)
    return [URL.format(today), URL.format(last_month)]


def main():
    TARGET.parent.mkdir(exist_ok=True)
    partial = TARGET.with_suffix('.part')
    for url in editions():
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'SeaSlugs build'})
            with urllib.request.urlopen(request, timeout=60) as response, gzip.GzipFile(fileobj=response) as data, \
                    open(partial, 'wb') as out:
                shutil.copyfileobj(data, out)
            import maxminddb
            maxminddb.open_database(str(partial)).close()   # a broken download never replaces a good file
            partial.replace(TARGET)
            print(f'country database: {url}')
            return 0
        except Exception as error:  # noqa: BLE001 -- any failure: try the next edition
            print(f'country database: {url} failed ({error})', file=sys.stderr)
            partial.unlink(missing_ok=True)
    print('country database: not updated' + (' (keeping the existing file)' if TARGET.exists() else ''), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
