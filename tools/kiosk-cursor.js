/* Kiosk-Mauszeiger: nach Inaktivität ausblenden, bei Bewegung sofort wieder da.
 *
 * REFERENZ-DATEI. Derselbe Block steht inline in allen Kiosk-Seiten:
 *   - templates/kiosk.html                    (Folien / Slideshow)
 *   - terminboard/templates/board.html        (Terminboard)
 *   - tools/safety-cross/templates/base.html  (Safety Cross)
 * Änderungen hier UND dort machen (test_cursor_unified.py prüft das).
 *
 * Idle-Zeit:  ?cursor_idle=<Sekunden>  (der Anzeige-Router hängt das an)
 *             oder data-cursor-idle am <html>-Element, sonst 30 Sekunden.
 *
 * Hinweis: Der Kiosk darf den Cursor NICHT dauerhaft unsichtbar machen
 * (kein transparentes X11-Cursor-Thema, kein `unclutter -idle 0`) — sonst
 * kann er beim Bewegen nicht wiederkommen.
 */
(function () {
  var q = new URLSearchParams(location.search).get('cursor_idle');
  var n = parseInt(q || document.documentElement.dataset.cursorIdle || '30', 10);
  /* 0 = Zeiger nie ausblenden (Wartungsbetrieb der Anzeige) */
  var MS = (isNaN(n) ? 30 : n) * 1000;
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
  /* Der Kiosk-Rahmen erfaehrt keine Ereignisse innerhalb eines bedienbaren
     iframes. Deshalb jede echte Bedienung nach oben melden. Nur mousemove zu
     melden reicht nicht: beim Tippen lief sonst der Eltern-Timer weiter und
     sein synthetischer Cursor-Klick nahm dem Eingabefeld kurz den Fokus. */
  ['mousemove', 'mousedown', 'wheel', 'keydown', 'touchstart', 'input', 'change', 'focusin'].forEach(function (e) {
    document.addEventListener(e, function () {
      show();
      try {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({ lhtpi: 'aktiv' }, '*');
        }
      } catch (err) {}
    }, true);
  });
  if (MS) timer = setTimeout(hide, MS);
})();
