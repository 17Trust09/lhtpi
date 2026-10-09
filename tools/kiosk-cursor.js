/* Kiosk-Mauszeiger: nach Inaktivität ausblenden, bei Bewegung sofort wieder da.
 *
 * REFERENZ-DATEI. Derselbe Block steht inline in allen Kiosk-Seiten:
 *   - templates/kiosk.html                    (Folien / Slideshow)
 *   - terminboard/templates/board.html        (Terminboard)
 *   - tools/safety-cross/templates/base.html  (Safety Cross)
 * Änderungen hier UND dort machen (test_cursor_unified.py prüft das).
 *
 * Idle-Zeit:  ?cursor_idle=<Sekunden>  (der Anzeige-Router hängt das an)
 *             oder data-cursor-idle am <html>-Element, sonst 3 Sekunden.
 *
 * Hinweis: Der Kiosk darf den Cursor NICHT dauerhaft unsichtbar machen
 * (kein transparentes X11-Cursor-Thema, kein `unclutter -idle 0`) — sonst
 * kann er beim Bewegen nicht wiederkommen.
 */
(function () {
  var q = new URLSearchParams(location.search).get('cursor_idle');
  var MS = (parseInt(q || document.documentElement.dataset.cursorIdle || '3', 10) || 3) * 1000;
  var timer;
  function hide() {
    if (document.getElementById('_kh')) return;
    var s = document.createElement('style');
    s.id = '_kh';
    s.textContent = '*,html,body{cursor:none!important}';
    document.head.appendChild(s);
  }
  function show() {
    var s = document.getElementById('_kh');
    if (s) s.remove();
    clearTimeout(timer);
    timer = setTimeout(hide, MS);
  }
  ['mousemove', 'mousedown', 'wheel', 'keydown', 'touchstart'].forEach(function (e) {
    document.addEventListener(e, show, true);
  });
  timer = setTimeout(hide, MS);
})();
