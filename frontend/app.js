const API_BASE = 'http://127.0.0.1:8000';
const DEFAULT_HEADERS = { 'X-User-Id': '1' };

async function api(path, options = {}) {
  const headers = { ...DEFAULT_HEADERS, ...(options.headers || {}) };
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  const ct = res.headers.get('content-type') || '';
  if (!res.ok) {
    if (ct.includes('application/json')) {
      const data = await res.json();
      throw new Error(data.detail || JSON.stringify(data));
    }
    throw new Error(await res.text());
  }

  if (!ct.includes('application/json')) return res;
  return res.json();
}

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    const data = await api('/skills/upload', { method: 'POST', body: form });
    document.getElementById('uploadResult').textContent = JSON.stringify(data, null, 2);
    loadSkills();
  } catch (err) {
    document.getElementById('uploadResult').textContent = err.message;
  }
});

async function loadSkills() {
  const el = document.getElementById('skills');
  el.innerHTML = '';
  try {
    const data = await api('/skills');
    data.forEach((s) => {
      const li = document.createElement('li');
      li.innerHTML = `<strong>${s.name}</strong> | 最新版本: v${s.latest_version} | 下载: ${s.download_count} | 安全分: ${s.security_score ?? '-'}
      <button data-id="${s.id}" class="detailBtn">详情</button>`;
      el.appendChild(li);
    });
  } catch (err) {
    el.innerHTML = `<li>${err.message}</li>`;
  }
}

document.getElementById('refreshSkills').addEventListener('click', loadSkills);

document.getElementById('skills').addEventListener('click', async (e) => {
  if (!e.target.classList.contains('detailBtn')) return;
  const id = e.target.getAttribute('data-id');
  const detail = await api(`/skills/${id}`);
  const versionText = detail.versions
    .map((v) => `v${v.version_no} (id=${v.id}, score=${v.security_score})`)
    .join('\n');
  alert(`Skill: ${detail.name}\n可见性: ${detail.visibility_type}\n版本:\n${versionText}`);
});

async function loadLeaderboard() {
  const el = document.getElementById('leaderboard');
  el.innerHTML = '';
  try {
    const data = await api('/leaderboard/downloads');
    data.forEach((x) => {
      const li = document.createElement('li');
      li.textContent = `${x.name} - ${x.downloads} 次`;
      el.appendChild(li);
    });
  } catch (err) {
    el.innerHTML = `<li>${err.message}</li>`;
  }
}

document.getElementById('refreshLeaderboard').addEventListener('click', loadLeaderboard);

document.getElementById('generateForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  try {
    const data = await api('/skills/generate', { method: 'POST', body: form });
    document.getElementById('generateResult').textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    document.getElementById('generateResult').textContent = err.message;
  }
});

document.getElementById('browseForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const skillId = form.get('skill_id');
  const versionId = form.get('version_id');
  const filesEl = document.getElementById('files');
  filesEl.innerHTML = '';
  try {
    const rows = await api(`/skills/${skillId}/versions/${versionId}/files`);

    const downloadLi = document.createElement('li');
    const downloadBtn = document.createElement('button');
    downloadBtn.textContent = '下载该版本';
    downloadBtn.addEventListener('click', () => {
      window.open(`${API_BASE}/skills/${skillId}/download/${versionId}`, '_blank');
    });
    downloadLi.appendChild(downloadBtn);
    filesEl.appendChild(downloadLi);

    rows.forEach((r) => {
      const li = document.createElement('li');
      li.innerHTML = `${r.is_dir ? '📁' : '📄'} ${r.path} (${r.size} bytes)`;
      if (!r.is_dir) {
        const btn = document.createElement('button');
        btn.textContent = '查看';
        btn.addEventListener('click', async () => {
          const data = await api(
            `/skills/${skillId}/versions/${versionId}/files/content?path=${encodeURIComponent(r.path)}`,
          );
          document.getElementById('fileContent').textContent = data.content_preview || '<empty>';
        });
        li.appendChild(btn);
      }
      filesEl.appendChild(li);
    });
  } catch (err) {
    filesEl.innerHTML = `<li>${err.message}</li>`;
  }
});

loadSkills();
loadLeaderboard();
