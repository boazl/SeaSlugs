// A YouTube video that will not play on other sites (embedding turned off, a copyright claim, a removed or
// private video) shows YouTube's own "This video is unavailable". Here every embedded player tells the page when
// that happens (the YouTube IFrame API's onError), and the player is replaced by the observation's photo -- or
// YouTube's still of the video when there is no photo -- linking to the video on YouTube.
// Usage: an iframe with data-fallback-image="<url>" (and optionally data-fallback-alt) is handled on its own;
// a player made later from JS calls window.youtubeFallback(iframe, imageUrl, alt).
(function () {
    var pending = [], loading = false;
    var en = (document.documentElement.lang || '').indexOf('en') === 0;
    var css = '.video-fallback{position:absolute;inset:0;display:block;background:#000;color:#fff;text-decoration:none}'
        + '.video-fallback img{display:block;width:100%;height:100%;object-fit:cover}'
        + '.video-fallback span{position:absolute;bottom:14px;inset-inline-start:14px;background:#000c;padding:7px 14px;border-radius:7px;font-size:15px}'
        + '.video-fallback:hover span{background:#000}';
    function idOf(src) {
        var m = /\/embed\/([\w-]{11})/.exec(src || '');
        return m ? m[1] : '';
    }
    function apiSrc(src) {
        var url = new URL(src, location.href);
        url.searchParams.set('enablejsapi', '1');
        url.searchParams.set('origin', location.origin);
        return url.toString();
    }
    function swap(iframe, image, alt) {
        if (!iframe.isConnected) return;
        if (!document.getElementById('video-fallback-style')) {
            var style = document.createElement('style');
            style.id = 'video-fallback-style'; style.textContent = css;
            document.head.appendChild(style);
        }
        var id = idOf(iframe.src);
        var link = document.createElement('a');
        link.className = 'video-fallback';
        link.href = 'https://www.youtube.com/watch?v=' + id;
        link.target = '_blank'; link.rel = 'noopener';
        var img = document.createElement('img');
        img.src = image || ('https://i.ytimg.com/vi/' + id + '/hqdefault.jpg');
        img.alt = alt || '';
        var label = document.createElement('span');
        label.textContent = en ? 'Watch on YouTube ↗' : 'צפייה בסרטון ב-YouTube ↗';
        link.append(img, label);
        var box = iframe.parentElement;
        if (box && getComputedStyle(box).position === 'static') box.style.position = 'relative';
        iframe.replaceWith(link);
    }
    function watch(item) {
        try {
            new YT.Player(item.iframe, { events: { onError: function () { swap(item.iframe, item.image, item.alt); } } });
        } catch (_) {}
    }
    function load() {
        if (window.YT && window.YT.Player) { pending.splice(0).forEach(watch); return; }
        if (loading) return;
        loading = true;
        var previous = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () {
            if (typeof previous === 'function') previous();
            pending.splice(0).forEach(watch);
        };
        var script = document.createElement('script');
        script.src = 'https://www.youtube.com/iframe_api'; script.async = true;
        document.head.appendChild(script);
    }
    window.youtubeFallback = function (iframe, image, alt) {
        if (!iframe || !idOf(iframe.src)) return;
        if (iframe.src.indexOf('enablejsapi=1') < 0) iframe.src = apiSrc(iframe.src);
        pending.push({ iframe: iframe, image: image, alt: alt });
        load();
    };
    function scan() {
        document.querySelectorAll('iframe[data-fallback-image]').forEach(function (f) {
            window.youtubeFallback(f, f.dataset.fallbackImage, f.dataset.fallbackAlt);
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', scan); else scan();
})();
