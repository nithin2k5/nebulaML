"use client";

import { useEffect, useRef } from "react";

/**
 * Run `callback` on an interval, but only when it is worth running.
 *
 * Three things the raw `setInterval` calls this replaces all got wrong:
 *
 *  - They ran whether or not the browser tab was visible. A backgrounded
 *    project page kept hitting /api/training/jobs every three seconds for as
 *    long as it stayed open, and every one of those requests costs a
 *    get_current_user database round trip out of a pool of ten.
 *  - They ran at the same rate whether a job was in flight or the project had
 *    been idle for a week. `idleIntervalMs` backs off when there is nothing
 *    to watch, and the caller flips `active` when there is.
 *  - They could overlap: a tick fired every interval regardless of whether the
 *    previous request had come back, so a slow endpoint queued up requests
 *    behind each other. Ticks are now skipped while one is still in flight.
 *
 * The callback is held in a ref, so passing a fresh closure on every render —
 * which every caller does — does not restart the timer.
 *
 * @param {() => (void|Promise<void>)} callback  what to run each tick
 * @param {object}   options
 * @param {number}   options.intervalMs      cadence while `active` (default 3000)
 * @param {number}   options.idleIntervalMs  cadence while not `active`; 0 disables
 *                                           polling entirely when idle (default 30000)
 * @param {boolean}  options.active          is there something worth watching
 * @param {boolean}  options.enabled         master switch (e.g. wait for a token)
 * @param {boolean}  options.runImmediately  fire once on mount (default true)
 */
export function usePolling(
  callback,
  {
    intervalMs = 3000,
    idleIntervalMs = 30000,
    active = true,
    enabled = true,
    runImmediately = true,
  } = {}
) {
  const callbackRef = useRef(callback);
  const inFlightRef = useRef(false);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    if (!enabled) return;

    const period = active ? intervalMs : idleIntervalMs;
    if (!period) return; // idle and idleIntervalMs === 0: stop entirely

    let cancelled = false;

    const tick = async () => {
      if (cancelled) return;
      // Nothing to repaint behind a hidden tab; the visibility listener below
      // fires a catch-up tick the moment the user comes back.
      if (typeof document !== "undefined" && document.hidden) return;
      if (inFlightRef.current) return;

      inFlightRef.current = true;
      try {
        await callbackRef.current();
      } finally {
        inFlightRef.current = false;
      }
    };

    if (runImmediately) tick();
    const id = setInterval(tick, period);

    const onVisible = () => {
      if (typeof document !== "undefined" && !document.hidden) tick();
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisible);
    }

    return () => {
      cancelled = true;
      clearInterval(id);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisible);
      }
    };
    // `callback` is deliberately absent: it lives in a ref so a new closure
    // each render does not tear down and rebuild the timer.
  }, [intervalMs, idleIntervalMs, active, enabled, runImmediately]);
}

export default usePolling;
