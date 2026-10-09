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
  var n = parseInt(q || document.documentElement.dataset.cursorIdle || '3', 10);
  /* 0 = Zeiger nie ausblenden (Wartungsbetrieb der Anzeige) */
  var MS = (isNaN(n) ? 3 : n) * 1000;
  var timer;
  function hide() {
    if (!MS) return;
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
    if (MS) timer = setTimeout(hide, MS);
  }
  ['mousemove', 'mousedown', 'wheel', 'keydown', 'touchstart'].forEach(function (e) {
    document.addEventListener(e, show, true);
  });
  /* Der Kiosk-Rahmen erfaehrt nichts von Bewegungen im Tool, wenn der Rahmen
     Eingaben annimmt (Wartungsbetrieb). Deshalb melden wir sie ihm - darauf
     erscheint der Wartungs-Knopf. */
  try {
    if (window.parent && window.parent !== window) {
      document.addEventListener('mousemove', function () {
        window.parent.postMessage({ lhtpi: 'maus' }, '*');
      }, true);
    }
  } catch (e) {}
  if (MS) timer = setTimeout(hide, MS);
})();
