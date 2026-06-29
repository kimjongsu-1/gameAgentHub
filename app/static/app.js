const el = (id) => document.getElementById(id);

function taskRow(task) {
  return `<div class="row"><strong>${escapeHtml(task.title)}</strong><span class="status">${task.status}</span><small>${escapeHtml(task.assignee_role)} · ${escapeHtml(task.task_type)}</small></div>`;
}

function approvalRow(item) {
  const imagePattern = /\.(png|jpe?g|gif|webp)$/i;
  const previews = (item.preview_paths || []).filter((path) => imagePattern.test(path)).slice(0, 5);
  const images = previews.length
    ? `<div class="preview-strip">${previews.map((path) => `<img src="/workspace-files/${encodeURI(path)}" alt="승인 미리보기">`).join("")}</div>`
    : "";
  return `<article class="approval-card" data-approval-id="${item.id}">
    <div class="row"><strong>${escapeHtml(item.approval_type)}</strong><span class="status">${item.status}</span><small>${escapeHtml(item.summary)}</small></div>
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
  return `<div class="row"><strong>${escapeHtml(item.target_thread_title)}</strong><span class="status">${item.status}</span><small>${escapeHtml(item.target_role)} · 시도 ${item.attempts}회${item.last_error ? ` · ${escapeHtml(item.last_error)}` : ""}</small>${retry}</div>`;
}

function runtimeRow(item) {
  return `<div class="row"><strong>${escapeHtml(item.asset_id || item.task_id)}</strong><span class="status">${item.status}</span><small>${escapeHtml(item.report_path)}</small></div>`;
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
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

    const providers = ["claude", "openai"];
    el("costs").innerHTML = providers.map((provider) => {
      const spent = Number(data.monthly_cost_usd[provider] || 0);
      const hard = Number(data.budgets[provider]?.hard || 0);
      return `<div class="cost-card"><small>${provider.toUpperCase()}</small><strong>$${spent.toFixed(2)}</strong><span class="subtitle">한도 ${hard ? `$${hard.toFixed(2)}` : "미설정"}</span></div>`;
    }).join("");
    el("gateway").innerHTML = `<p class="subtitle">Gateway: ${gateway.external_calls_enabled ? "외부 호출 허용" : "외부 호출 차단"} · 기본 정책 ${gateway.default_policy}</p>`;
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

loadDashboard();
setInterval(loadDashboard, 30000);
