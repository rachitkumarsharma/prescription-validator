(() => {
  "use strict";
  const EYES = ["right_eye", "left_eye"];
  const FIELDS = ["sph", "cyl", "axis"];
  const SAMPLE = {
    right_eye: { sph: "-2.00", cyl: "-0.50", axis: "90" },
    left_eye: { sph: "1.25", cyl: "-0.75", axis: "180" },
  };

  const form = document.getElementById("rx-form");
  const banner = document.getElementById("banner");
  const validateBtn = document.getElementById("validate-btn");
  const sampleBtn = document.getElementById("sample-btn");
  const resetBtn = document.getElementById("reset-btn");
  let inFlight = false;

  const input = (eye, f) => document.getElementById(`${eye}-${f}`);
  const errBox = (eye, f) => document.getElementById(`err-${eye}-${f}`);

  function collect() {
    const body = {};
    for (const eye of EYES) {
      body[eye] = {};
      for (const f of FIELDS) body[eye][f] = input(eye, f).value;
    }
    return body;
  }

  function clearErrors() {
    for (const eye of EYES) for (const f of FIELDS) {
      errBox(eye, f).textContent = "";
      input(eye, f).removeAttribute("aria-invalid");
    }
  }

  function showBanner(kind, text) {
    banner.className = `banner ${kind}`;
    banner.textContent = text; // textContent: never innerHTML
  }

  function hideBanner() {
    banner.className = "banner hidden";
    banner.textContent = "";
  }

  function setLoading(on) {
    inFlight = on;
    validateBtn.disabled = on;
    validateBtn.textContent = on ? "Validating\u2026" : "Validate Prescription";
  }

  function showFieldErrors(errors) {
    for (const [key, msg] of Object.entries(errors)) {
      const [eye, f] = key.split(".");
      if (!EYES.includes(eye) || !FIELDS.includes(f)) continue;
      errBox(eye, f).textContent = String(msg);
      input(eye, f).setAttribute("aria-invalid", "true");
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    if (inFlight) return; // prevent duplicate submissions
    setLoading(true);
    clearErrors();
    showBanner("loading", "Validating\u2026");

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const res = await fetch("/api/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collect()),
        signal: controller.signal,
      });
      let data = null;
      try { data = await res.json(); } catch (_) { /* non-JSON body */ }

      const wellFormed = data && typeof data === "object" &&
        typeof data.valid === "boolean" && data.errors && typeof data.errors === "object";

      if (!res.ok) {
        const msg = data && typeof data.message === "string" ? data.message : `Request failed (HTTP ${res.status}).`;
        showBanner("failure", msg);
      } else if (!wellFormed) {
        showBanner("failure", "Unexpected response from the server.");
      } else if (data.valid) {
        showBanner("success", "\u2713 " + String(data.message));
      } else {
        showFieldErrors(data.errors);
        showBanner("failure", "\u2717 " + String(data.message));
      }
    } catch (err) {
      showBanner("failure", err && err.name === "AbortError"
        ? "The request timed out. Please try again."
        : "Could not reach the server. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
      setLoading(false);
    }
  }

  function loadSample() {
    for (const eye of EYES) for (const f of FIELDS) input(eye, f).value = SAMPLE[eye][f];
    clearErrors();
    hideBanner();
  }

  function reset() {
    form.reset();
    clearErrors();
    hideBanner();
    setLoading(false);
    input("right_eye", "sph").focus();
  }

  async function loadRules() {
    try {
      const res = await fetch("/api/config");
      if (!res.ok) return;
      const c = await res.json();
      const items = [
        `SPH: ${c.sph[0]} to +${c.sph[1]}, steps of ${c.step}`,
        `CYL: ${c.cyl[0]} to +${c.cyl[1]}, steps of ${c.step}`,
        `Axis: integer ${c.axis[0]}\u2013${c.axis[1]}; required only when CYL is not zero`,
      ];
      const ul = document.getElementById("rules");
      ul.replaceChildren(...items.map((t) => { const li = document.createElement("li"); li.textContent = t; return li; }));
    } catch (_) { /* keep static fallback text */ }
  }

  form.addEventListener("submit", onSubmit);
  sampleBtn.addEventListener("click", loadSample);
  resetBtn.addEventListener("click", reset);
  loadRules();
})();
