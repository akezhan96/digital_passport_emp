
      /* Applied before the first paint. Left to React this would run after the
         page had already been painted in the wrong theme, and every load would
         start with a white flash on a dark screen. */
      (function () {
        try {
          var stored = localStorage.getItem('hrts.theme');
          if (stored === 'light' || stored === 'dark') {
            document.documentElement.setAttribute('data-theme', stored);
          }
        } catch (e) { /* private mode: fall through to the system setting */ }
      })();
    