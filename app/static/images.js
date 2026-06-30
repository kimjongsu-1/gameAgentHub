const byId = (id) => document.getElementById(id);
const categoryLabels = {
  character: "캐릭터", monster: "몬스터", background: "맵·배경",
  vfx: "이펙트", item: "아이템", qa: "QA", other: "기타",
};
const designGroups = [
  { id: "entity_design", label: "캐릭터 · 몬스터 · NPC", description: "캐릭터 원화, 몬스터, NPC 초상과 애니메이션", className: "entity" },
  { id: "world_item_design", label: "맵 · 배경화면 · 아이템", description: "스테이지 배경, 맵 레이어, 아이콘과 아이템", className: "world" },
  { id: "skill_vfx_design", label: "스킬 이펙트 · 스킬", description: "전투 스킬, 타격 효과와 VFX 애니메이션", className: "skill" },
];
let libraryItems = [];
let selectedDesignGroup = "all";

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function mediaUrl(path) {
  return `/workspace-files/${path.split("/").map(encodeURIComponent).join("/")}`;
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function itemStatus(item) {
  if (item.asset_status) return item.asset_status;
  if (item.approval_statuses.includes("APPROVED")) return "APPROVED";
  if (item.approval_statuses.includes("PENDING")) return "PENDING";
  return "unregistered";
}

function filteredItems() {
  const query = byId("image-search").value.trim().toLowerCase();
  const category = byId("category-filter").value;
  const status = byId("status-filter").value;
  const includeSources = byId("source-toggle").checked;
  return libraryItems.filter((item) => {
    const haystack = `${item.file_name} ${item.path} ${item.asset_id || ""}`.toLowerCase();
    return (!query || haystack.includes(query))
      && (category === "all" || item.category === category)
      && (status === "all" || itemStatus(item) === status)
      && (selectedDesignGroup === "all" || item.design_group === selectedDesignGroup)
      && (includeSources || !item.is_source);
  });
}

function card(item, index) {
  const status = itemStatus(item);
  const statusClass = status === "QA_PASS" || status === "APPROVED" ? "pass" : status === "PENDING" ? "pending" : "";
  return `<button class="image-card" type="button" data-image-index="${index}" aria-label="${escapeHtml(item.file_name)} 크게 보기">
    <span class="image-frame">
      <img src="${mediaUrl(item.path)}" alt="${escapeHtml(item.file_name)}" loading="lazy">
      ${item.is_animated ? '<span class="animated-badge">GIF</span>' : ""}
    </span>
    <span class="image-card-info">
      <strong>${escapeHtml(item.file_name)}</strong>
      <small>${escapeHtml(item.asset_id || item.path)}</small>
      <span class="image-tags">
        <span class="image-tag">${escapeHtml(categoryLabels[item.category] || item.category)}</span>
        <span class="image-tag ${statusClass}">${escapeHtml(status)}</span>
        <span class="image-tag">${formatBytes(item.size_bytes)}</span>
      </span>
    </span>
  </button>`;
}

function render() {
  const items = filteredItems();
  byId("result-count").textContent = `${items.length}개`;
  byId("library-message").textContent = items.length === libraryItems.length
    ? "전체 이미지"
    : `전체 ${libraryItems.length}개 중 필터 결과`;
  const groupsToRender = selectedDesignGroup === "all"
    ? designGroups
    : designGroups.filter((group) => group.id === selectedDesignGroup);
  byId("image-grid").innerHTML = items.length
    ? groupsToRender.map((group) => {
        const groupItems = items.filter((item) => item.design_group === group.id);
        if (!groupItems.length) return "";
        return `<section class="design-lane ${group.className}" aria-labelledby="lane-${group.id}">
          <header class="design-lane-header">
            <div><p class="eyebrow">DESIGN SPECIALIZATION</p><h2 id="lane-${group.id}">${group.label}</h2><p>${group.description}</p></div>
            <strong>${groupItems.length}개</strong>
          </header>
          <div class="image-grid">${groupItems.map((item) => card(item, libraryItems.indexOf(item))).join("")}</div>
        </section>`;
      }).join("")
    : '<div class="image-empty">조건에 맞는 이미지가 없습니다.</div>';

  designGroups.forEach((group) => {
    byId(`group-count-${group.id}`).textContent = libraryItems.filter((item) => item.design_group === group.id).length;
  });
  byId("group-count-all").textContent = libraryItems.length;
}

function metaRow(label, value) {
  return value === null || value === undefined || value === ""
    ? ""
    : `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function openLightbox(item) {
  byId("lightbox-image").src = mediaUrl(item.path);
  byId("lightbox-title").textContent = item.file_name;
  byId("lightbox-path").textContent = item.path;
  byId("lightbox-meta").innerHTML = [
    metaRow("종류", categoryLabels[item.category] || item.category),
    metaRow("에셋 ID", item.asset_id),
    metaRow("에셋 상태", item.asset_status),
    metaRow("승인 상태", item.approval_statuses.join(", ")),
    metaRow("프레임", item.frame_count),
    metaRow("FPS", item.fps),
    metaRow("파일 크기", formatBytes(item.size_bytes)),
    metaRow("수정 시각", new Date(item.modified_at).toLocaleString("ko-KR")),
  ].join("");
  byId("image-lightbox").hidden = false;
  document.body.classList.add("lightbox-open");
  byId("lightbox-close").focus();
}

function closeLightbox() {
  byId("image-lightbox").hidden = true;
  document.body.classList.remove("lightbox-open");
}

async function loadLibrary() {
  try {
    const response = await fetch("/api/image-library");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    libraryItems = data.items;
    byId("library-count").textContent = `전체 ${data.total}개`;
    render();
  } catch (error) {
    byId("library-count").textContent = "불러오기 실패";
    byId("library-message").textContent = error.message;
    byId("image-grid").innerHTML = '<div class="image-empty">이미지 목록을 불러오지 못했습니다.</div>';
  }
}

["image-search", "category-filter", "status-filter", "source-toggle"].forEach((id) => {
  byId(id).addEventListener(id === "image-search" ? "input" : "change", render);
});
byId("design-group-filter").addEventListener("click", (event) => {
  const target = event.target.closest("[data-design-group]");
  if (!target) return;
  selectedDesignGroup = target.dataset.designGroup;
  document.querySelectorAll("[data-design-group]").forEach((button) => {
    const active = button === target;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  render();
});
byId("image-grid").addEventListener("click", (event) => {
  const target = event.target.closest("[data-image-index]");
  if (target) openLightbox(libraryItems[Number(target.dataset.imageIndex)]);
});
byId("lightbox-close").addEventListener("click", closeLightbox);
byId("lightbox-backdrop").addEventListener("click", closeLightbox);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !byId("image-lightbox").hidden) closeLightbox();
});
byId("copy-path").addEventListener("click", async () => {
  await navigator.clipboard.writeText(byId("lightbox-path").textContent);
  byId("copy-path").textContent = "복사됨";
  window.setTimeout(() => { byId("copy-path").textContent = "경로 복사"; }, 1200);
});

loadLibrary();
