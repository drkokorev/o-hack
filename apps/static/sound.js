/* A few short, locally generated sounds; nothing plays on page load. */
(() => {
  const button = document.getElementById("sound-toggle");
  const Audio = window.AudioContext || window.webkitAudioContext;
  const cooldownMs = 2600;
  let enabled = true, context = null, master = null, lastPlayed = -Infinity;
  try { enabled = localStorage.getItem("odin.sound") !== "off"; } catch (_) {}
  if (!Audio) enabled = false;
  function update() {
    button.disabled = !Audio;
    button.setAttribute("aria-pressed", String(enabled));
    button.setAttribute("aria-label", enabled ? "Выключить звуки" : "Включить звуки");
    button.title = !Audio ? "Звуки недоступны" : enabled ? "Звуки включены" : "Звуки выключены";
    if (master && context) master.gain.setTargetAtTime(enabled ? 1 : 0, context.currentTime, .025);
  }
  function play(kind = "select") {
    if (!enabled || !Audio || performance.now() - lastPlayed < cooldownMs) return;
    lastPlayed = performance.now();
    try {
      if (!context) { context = new Audio(); master = context.createGain(); master.gain.value = 1; master.connect(context.destination); }
      if (context.state === "suspended") context.resume().catch(() => {});
      const now = context.currentTime;
      if (kind === "sea") {
        const duration = 1.5, buffer = context.createBuffer(1, context.sampleRate * duration, context.sampleRate);
        const samples = buffer.getChannelData(0);
        for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;
        const source = context.createBufferSource(), filter = context.createBiquadFilter(), gain = context.createGain();
        source.buffer = buffer; filter.type = "lowpass"; filter.frequency.value = 430;
        gain.gain.setValueAtTime(.0001, now); gain.gain.exponentialRampToValueAtTime(.018, now + .5);
        gain.gain.exponentialRampToValueAtTime(.0001, now + duration);
        source.connect(filter); filter.connect(gain); gain.connect(master); source.start(now); source.stop(now + duration);
      } else {
        const oscillator = context.createOscillator(), gain = context.createGain();
        oscillator.type = "sine"; oscillator.frequency.value = kind === "event" ? 523.25 : 392;
        gain.gain.setValueAtTime(.0001, now); gain.gain.exponentialRampToValueAtTime(.025, now + .04);
        gain.gain.exponentialRampToValueAtTime(.0001, now + .5);
        oscillator.connect(gain); gain.connect(master); oscillator.start(now); oscillator.stop(now + .5);
      }
    } catch (_) { /* Sound is optional; interaction always continues. */ }
  }
  button.addEventListener("click", () => {
    enabled = !enabled;
    try { localStorage.setItem("odin.sound", enabled ? "on" : "off"); } catch (_) {}
    update();
  });
  document.addEventListener("click", (event) => {
    const target = event.target.closest("[data-sound]");
    if (target && ["event", "sea", "select"].includes(target.dataset.sound)) play(target.dataset.sound);
  }, true);
  update();
})();
