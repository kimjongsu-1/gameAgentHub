const byId = (id) => document.getElementById(id);
let motionItems = [];

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function option(value) {
  return `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`;
}

function populateFilters() {
  const motions = [...new Set(motionItems.map((item) => item.motion))].sort();
  const families = [...new Set(motionItems.map((item) => item.family).filter(Boolean))].sort();
  const palettes = [...new Set(motionItems.map((item) => item.palette).filter(Boolean))].sort();
  byId("motion-filter").insertAdjacentHTML("beforeend", motions.map(option).join(""));
  byId("family-filter").insertAdjacentHTML("beforeend", families.map(option).join(""));
  byId("palette-filter").insertAdjacentHTML("beforeend", palettes.map(option).join(""));
}

function filteredItems() {
  const query = byId("motion-search").value.trim().toLowerCase();
  const subject = byId("subject-filter").value;
  const motion = byId("motion-filter").value;
  const family = byId("family-filter").value;
  const palette = byId("palette-filter").value;
  return motionItems.filter((item) => {
    const haystack = `${item.subject_id} ${item.subject_label} ${item.motion} ${item.family || ""} ${item.palette || ""}`.toLowerCase();
    return (!query || haystack.includes(query))
      && (subject === "all" || item.subject_type === subject)
      && (motion === "all" || item.motion === motion)
      && (family === "all" || item.family === family)
      && (palette === "all" || item.palette === palette);
  });
}

function card(item) {
  const qaLabel = item.stability_status === "REVISION_REQUIRED" ? "REWORK" : "QA PASS";
  return `<button class="motion-card" type="button" data-motion-id="${escapeHtml(item.id)}" aria-label="${escapeHtml(item.subject_label)} ${escapeHtml(item.motion_label)} 크게 보기">
    <span class="motion-stage">
      <img src="${item.url}" alt="${escapeHtml(item.subject_label)} ${escapeHtml(item.motion_label)} 6fps GIF" loading="lazy">
      <span class="fps-badge">${item.fps} FPS</span><span class="qa-badge ${item.stability_status === "REVISION_REQUIRED" ? "fail" : ""}">${qaLabel}</span>
    </span>
    <span class="motion-info">
      <strong>${escapeHtml(item.subject_label)} · ${escapeHtml(item.motion_label)}</strong>
      <small>${escapeHtml(item.subject_id)}</small>
      <span class="motion-tags"><span>${item.frame_count || "-"} frames</span>${item.height_variation_percent !== null && item.height_variation_percent !== undefined ? `<span>scale ${item.height_variation_percent}%</span>` : ""}${item.family ? `<span>${escapeHtml(item.family)}</span>` : ""}${item.palette ? `<span>${escapeHtml(item.palette)}</span>` : ""}</span>
    </span>
  </button>`;
}

function render() {
  const items = filteredItems();
  byId("result-count").textContent = `${items.length}개 모션`;
  const sections = [
    ["character", "완성 캐릭터 모션"],
    ["monster", "완성 몬스터 모션"],
  ].map(([type, label]) => {
    const group = items.filter((item) => item.subject_type === type);
    if (!group.length) return "";
    return `<section class="motion-group" aria-labelledby="motion-${type}"><header><h2 id="motion-${type}">${label}</h2><strong>${group.length}개</strong></header><div class="motion-grid">${group.map(card).join("")}</div></section>`;
  }).join("");
  byId("motion-groups").innerHTML = sections || '<div class="motion-empty">선택한 조건의 완성 모션이 없습니다.</div>';
}

function openMotion(item) {
  byId("motion-dialog-image").src = item.url;
  byId("motion-dialog-title").textContent = `${item.subject_label} · ${item.motion_label}`;
  byId("motion-dialog-meta").textContent = `${item.frame_count || "-"} frames · ${item.fps}fps · QA ${item.qa_status} · ${item.approval_status}${item.height_variation_percent !== null && item.height_variation_percent !== undefined ? ` · scale ${item.height_variation_percent}%` : ""}`;
  byId("motion-dialog-path").textContent = item.path;
  byId("motion-lightbox").hidden = false;
}

function closeMotion() { byId("motion-lightbox").hidden = true; }

async function loadMotions() {
  try {
    const response = await fetch("/api/motion-gif-library");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    motionItems = data.items;
    byId("total-count").textContent = data.total;
    byId("character-count").textContent = data.character_count;
    byId("monster-count").textContent = data.monster_count;
    populateFilters();
    render();
  } catch (error) {
    byId("result-count").textContent = "불러오기 실패";
    byId("motion-groups").innerHTML = `<div class="motion-empty">${escapeHtml(error.message)}</div>`;
  }
}

["motion-search", "subject-filter", "motion-filter", "family-filter", "palette-filter"].forEach((id) => byId(id).addEventListener(id === "motion-search" ? "input" : "change", render));
byId("motion-groups").addEventListener("click", (event) => {
  const target = event.target.closest("[data-motion-id]");
  if (!target) return;
  const item = motionItems.find((candidate) => candidate.id === target.dataset.motionId);
  if (item) openMotion(item);
});
byId("motion-close").addEventListener("click", closeMotion);
byId("motion-backdrop").addEventListener("click", closeMotion);
document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMotion(); });
loadMotions();
