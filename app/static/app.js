const el = (id) => document.getElementById(id);

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function taskRow(task) {
  return `<div class="row"><strong>${escapeHtml(task.title)}</strong><span class="status">${escapeHtml(task.status)}</span><small>${escapeHtml(task.assignee_role)} · ${escapeHtml(task.task_type)}</small></div>`;
}

function approvalRow(item) {
  const imagePattern = /\.(png|jpe?g|gif|webp)$/i;
  const previews = (item.preview_paths || []).filter((path) => imagePattern.test(path)).slice(0, 5);
  const images = previews.length
    ? `<div class="preview-strip">${previews.map((path) => `<img src="/workspace-files/${encodeURI(path)}" alt="승인 미리보기">`).join("")}</div>`
    : "";
  return `<article class="approval-card" data-approval-id="${item.id}">
    <div class="row"><strong>${escapeHtml(item.approval_type)}</strong><span class="status">${escapeHtml(item.status)}</span><small>${escapeHtml(item.summary)}</small></div>
    ${images}
    <div class="approval-actions">
      <button class="approve" data-decision="APPROVED">승인</button>
      <button data-decision="REVISION_REQUIRED">재작업</button>
      <button class="reject" data-decision="REJECTED">거절</button>
    </div>
  </article>`;
}

function dispatchRow(item) {
  const retry = item.status === "FAILED"
    ? `<button class="retry-dispatch" data-dispatch-id="${item.id}">재시도</button>`
    : "";
  const error = item.last_error ? ` · ${escapeHtml(item.last_error)}` : "";
  return `<div class="row"><strong>${escapeHtml(item.target_thread_title)}</strong><span class="status">${escapeHtml(item.status)}</span><small>${escapeHtml(item.target_role)} · 시도 ${item.attempts}회${error}</small>${retry}</div>`;
}

function runtimeRow(item) {
  return `<div class="row"><strong>${escapeHtml(item.asset_id || item.task_id)}</strong><span class="status">${escapeHtml(item.status)}</span><small>${escapeHtml(item.report_path)}</small></div>`;
}

function superGrokPromptRow(item) {
  const promptId = `super-grok-prompt-${item.id}`;
  const negativeId = `super-grok-negative-${item.id}`;
  const image = item.reference_image_path
    ? `<img class="super-grok-image" src="/workspace-files/${encodeURI(item.reference_image_path)}" alt="SuperGrok reference image">`
    : "";
  return `<article class="super-grok-card">
    <div class="row">
      <strong>${escapeHtml(item.title)}</strong>
      <span class="status">${escapeHtml(item.status)}</span>
      <small>${escapeHtml(item.request_type)} · ${escapeHtml(item.reference_image_path)} · ${escapeHtml(item.package_path)}</small>
    </div>
    <div class="super-grok-body">
      ${image}
      <div class="prompt-stack">
        <label>SuperGrok prompt</label>
        <textarea id="${promptId}" readonly>${escapeHtml(item.prompt)}</textarea>
        <button class="copy-text" data-copy-target="${promptId}">프롬프트 복사</button>
        <label>Negative prompt</label>
        <textarea id="${negativeId}" readonly>${escapeHtml(item.negative_prompt || "")}</textarea>
        <button class="copy-text" data-copy-target="${negativeId}">네거티브 복사</button>
      </div>
    </div>
  </article>`;
}

function pipelineStageRow(stage) {
  const flags = [
    stage.configured ? "연결 완료" : "연결 필요",
    stage.paused ? "중지됨" : (stage.active ? "실행 중" : "대기"),
  ];
  const counts = Object.entries(stage.task_counts || {})
    .map(([name, value]) => `${name}:${value}`)
    .join(" · ") || "작업 없음";
  const description = stage.description ? `<small>${escapeHtml(stage.description)}</small>` : "";
  return `<div class="stage-card ${stage.configured ? "" : "needs-config"}">
    <strong>${escapeHtml(stage.thread_title)}</strong>
    <span>${flags.map(escapeHtml).join(" · ")}</span>
    <small>${escapeHtml(stage.role)} · ${escapeHtml(counts)}</small>
    ${description}
  </div>`;
}

function pmRoutingView(routing) {
  if (!routing) return `<p class="subtitle">PM 라우팅 상태를 불러올 수 없습니다.</p>`;
  const flow = (routing.flow || [])
    .map((item) => `<li><strong>${escapeHtml(item.owner)}</strong><span>${escapeHtml(item.action)}</span></li>`)
    .join("");
  const next = (routing.next_required_connections || [])
    .filter((item) => item.needed)
    .map((item) => `<li><strong>${escapeHtml(item.role)}</strong><span>${escapeHtml(item.action)}</span></li>`)
    .join("") || `<li><strong>필수 연결</strong><span>현재 추가 필수 연결 없음</span></li>`;
  const badges = [
    ["PM", routing.pm_owner],
    ["기획", routing.planning_mode === "user_direct" ? "사용자 직접" : routing.planning_mode],
    ["반복 QA", routing.repeated_qa_mode === "free_local_tools" ? "무료 로컬 도구" : routing.repeated_qa_mode],
    ["전달 방식", routing.dispatcher_mode === "manual" ? "수동" : routing.dispatcher_mode],
    ["Dispatcher", routing.dispatcher_status],
    ["게임개발", routing.game_development_locked ? "중지됨" : "대기"],
  ];
  return `<div class="pm-badges">${badges.map(([name, value]) => `<div><small>${escapeHtml(name)}</small><strong>${escapeHtml(value)}</strong></div>`).join("")}</div>
    <p class="subtitle">${escapeHtml(routing.routing_model)}</p>
    <div class="pm-columns">
      <div><h3>지시 흐름</h3><ol>${flow}</ol></div>
      <div><h3>남은 연결</h3><ol>${next}</ol></div>
    </div>`;
}

async function loadDashboard() {
  try {
    const [health, data, gateway] = await Promise.all([
      fetch("/health").then((r) => r.json()),
      fetch("/api/dashboard").then((r) => r.json()),
      fetch("/api/gateway/policy").then((r) => r.json()),
    ]);
    el("health").textContent = health.status === "ok" ? "시스템 정상" : "확인 필요";
    el("health").className = "health ok";

    const counts = data.counts || {};
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    const cards = [
      ["전체 작업", total],
      ["실행 중", (counts.RUNNING || 0) + (counts.DESIGNING || 0) + (counts.INTEGRATING || 0)],
      ["승인 대기", counts.WAITING_USER_APPROVAL || 0],
      ["재작업", counts.REVISION_REQUIRED || 0],
      ["QA 통과 에셋", data.asset_counts?.QA_PASS || 0],
    ];
    el("summary").innerHTML = cards.map(([name, value]) => `<div class="metric"><span>${name}</span><strong>${value}</strong></div>`).join("");

    const stages = data.pipeline_stages || [];
    el("pipeline-status").innerHTML = stages.length
      ? stages.map(pipelineStageRow).join("")
      : `<p class="subtitle">파이프라인 상태를 불러올 수 없습니다.</p>`;
    el("pm-routing").innerHTML = pmRoutingView(data.pm_routing);

    el("tasks").className = data.recent_tasks.length ? "list" : "list empty";
    el("tasks").innerHTML = data.recent_tasks.length ? data.recent_tasks.map(taskRow).join("") : "등록된 작업이 없습니다.";
    el("approval-count").textContent = data.pending_approvals.length;
    el("approvals").className = data.pending_approvals.length ? "list" : "list empty";
    el("approvals").innerHTML = data.pending_approvals.length ? data.pending_approvals.map(approvalRow).join("") : "승인 요청이 없습니다.";

    const activeDispatches = (data.recent_dispatches || []).filter((item) => ["PENDING", "CLAIMED", "FAILED"].includes(item.status));
    el("dispatch-count").textContent = activeDispatches.length;
    el("dispatches").className = data.recent_dispatches.length ? "list" : "list empty";
    el("dispatches").innerHTML = data.recent_dispatches.length ? data.recent_dispatches.map(dispatchRow).join("") : "전달 대기 작업이 없습니다.";

    const runtimeReports = data.recent_runtime_reports || [];
    el("runtime-count").textContent = runtimeReports.length;
    el("runtime-reports").className = runtimeReports.length ? "list" : "list empty";
    el("runtime-reports").innerHTML = runtimeReports.length ? runtimeReports.map(runtimeRow).join("") : "런타임 보고서가 없습니다.";

    const superGrokPrompts = data.recent_super_grok_prompts || [];
    el("super-grok-count").textContent = superGrokPrompts.length;
    el("super-grok-prompts").className = superGrokPrompts.length ? "list" : "list empty";
    el("super-grok-prompts").innerHTML = superGrokPrompts.length
      ? superGrokPrompts.map(superGrokPromptRow).join("")
      : "생성된 SuperGrok 요청 패키지가 없습니다.";

    const providers = ["claude", "openai"];
    el("costs").innerHTML = providers.map((provider) => {
      const spent = Number(data.monthly_cost_usd[provider] || 0);
      const hard = Number(data.budgets[provider]?.hard || 0);
      return `<div class="cost-card"><small>${provider.toUpperCase()}</small><strong>$${spent.toFixed(2)}</strong><span class="subtitle">한도 ${hard ? `$${hard.toFixed(2)}` : "미설정"}</span></div>`;
    }).join("");
    el("gateway").innerHTML = `<p class="subtitle">Gateway: ${gateway.external_calls_enabled ? "외부 호출 허용" : "외부 호출 차단"} · 기본 정책 ${gateway.default_policy} · 반복 QA는 무료 로컬 도구 우선</p>`;
  } catch (error) {
    el("health").textContent = "연결 실패";
    el("health").className = "health";
    console.error(error);
  }
}

async function decideApproval(approvalId, decision, button) {
  const labels = { APPROVED: "이 결과를 승인할까요?", REVISION_REQUIRED: "재작업을 요청할까요?", REJECTED: "이 결과를 거절할까요?" };
  if (!window.confirm(labels[decision])) return;
  const card = button.closest(".approval-card");
  card.querySelectorAll("button").forEach((item) => { item.disabled = true; });
  const response = await fetch(`/api/approvals/${approvalId}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, decided_by: "user_dashboard" }),
  });
  if (!response.ok) {
    const error = await response.json();
    window.alert(error.detail || "승인 처리에 실패했습니다.");
  }
  await loadDashboard();
}

async function retryDispatch(dispatchId) {
  const response = await fetch(`/api/dispatches/${dispatchId}/retry`, { method: "POST" });
  if (!response.ok) {
    const error = await response.json();
    window.alert(error.detail || "재시도 등록에 실패했습니다.");
  }
  await loadDashboard();
}

async function copyTextById(targetId) {
  const target = document.getElementById(targetId);
  if (!target) return;
  await navigator.clipboard.writeText(target.value || target.textContent || "");
}

async function createCharacterConsistencyTest(form) {
  const result = el("character-consistency-result");
  const button = form.querySelector("button[type='submit']");
  result.innerHTML = `<p class="subtitle">업로드와 큐 생성을 진행 중입니다...</p>`;
  button.disabled = true;
  try {
    const response = await fetch("/api/design/character-consistency-tests", {
      method: "POST",
      body: new FormData(form),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "통일성 테스트 큐 생성에 실패했습니다.");
    }
    result.innerHTML = `<div class="row">
      <strong>통일성 테스트 큐 생성 완료</strong>
      <span class="status">${escapeHtml(payload.dispatch.status)}</span>
      <small>작업 ${escapeHtml(payload.task.id)} · 참조 이미지 ${escapeHtml(payload.reference_image_path)}</small>
    </div>`;
    form.reset();
    await loadDashboard();
  } catch (error) {
    result.innerHTML = `<p class="subtitle">${escapeHtml(error.message)}</p>`;
  } finally {
    button.disabled = false;
  }
}

el("approvals").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-decision]");
  if (!button) return;
  const card = button.closest(".approval-card");
  decideApproval(card.dataset.approvalId, button.dataset.decision, button);
});

el("dispatches").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-dispatch-id]");
  if (!button) return;
  retryDispatch(button.dataset.dispatchId);
});

el("super-grok-prompts").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-copy-target]");
  if (!button) return;
  copyTextById(button.dataset.copyTarget);
});

el("character-consistency-form").addEventListener("submit", (event) => {
  event.preventDefault();
  createCharacterConsistencyTest(event.currentTarget);
});

loadDashboard();
setInterval(loadDashboard, 30000);
