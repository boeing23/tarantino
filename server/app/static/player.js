// Gapless shot player: two stacked <video> elements. One plays while the other preloads the next clip;
// they swap with a short crossfade. A shot whose clip has not arrived holds the last frame for its
// duration (or until the clip lands), so the screen never goes black.
function shotPlayer(videos, onChange) {
  let [front, back] = videos;
  let shots = [];
  let index = 0;
  let holding = false;
  let holdTimer = null;
  let sound = false;

  for (const v of videos) {
    v.playsInline = true;
    v.preload = "auto";
    v.addEventListener("ended", () => { if (v === front && !holding) play(index + 1); });
    v.addEventListener("timeupdate", () => { if (v === front) report(); });
  }

  function elapsed() {
    const before = shots.slice(0, index).reduce((n, s) => n + s.duration_s, 0);
    return before + (holding ? 0 : front.currentTime || 0);
  }

  function report() {
    const total = shots.reduce((n, s) => n + s.duration_s, 0);
    onChange({ index, holding, elapsed: elapsed(), total, line: shots[index]?.line ?? null });
  }

  function show(v) {
    v.style.opacity = "1";
    (v === front ? back : front).style.opacity = "0";
  }

  function preload(i) {
    const url = shots[i]?.video_url;
    if (url && back.dataset.src !== url) {
      back.dataset.src = url;
      back.src = url;
      back.load();
    }
  }

  function play(i) {
    clearTimeout(holdTimer);
    if (i >= shots.length) { // end of chapter: hold the last frame, no subtitle, until the next beat arrives
      index = shots.length;
      holding = true;
      report();
      return;
    }
    index = i;
    const url = shots[i].video_url;
    if (!url) {
      holding = true;
      front.pause();
      holdTimer = setTimeout(() => play(i + 1), shots[i].duration_s * 1000);
      report();
      return;
    }
    holding = false;
    if (back.dataset.src === url) {
      [front, back] = [back, front]; // the next clip is already buffered: swap
    } else {
      front.dataset.src = url;
      front.src = url;
    }
    front.currentTime = 0;
    front.muted = !sound;
    front.play().catch(() => {});
    show(front);
    back.pause();
    preload(i + 1);
    report();
  }

  return {
    load(newShots) {
      shots = newShots.map((s) => ({ ...s }));
      play(0);
    },
    addClip(shotId, url) {
      const i = shots.findIndex((s) => s.shot_id === shotId);
      if (i < 0) return;
      shots[i].video_url = url;
      if (i === index && holding) play(i);
      else if (i === index + 1) preload(i);
    },
    setSound(on) {
      sound = on;
      front.muted = !on;
      if (on) front.play().catch(() => {});
    },
  };
}
