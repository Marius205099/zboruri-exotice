// Tab-ul „Cu oprire 1–2 zile”: combinații cu bilete separate printr-un oraș-hub.
(() => {
  const S = {origins: new Set(), hubs: null, bags: true, shown: 30};
  let SD, DIRECT_BEST = {};

  const $ = id => document.getElementById(id);
  const price = c => S.bags ? c.total : c.tickets;
  const nightsTxt = n => n === 1 ? '1 noapte' : `${n} nopți`;
  const hubName = h => SD.hubs[h] || h;

  function chips(container, items, isOn, onClick) {
    container.innerHTML = '';
    items.forEach(([val, label]) => {
      const b = el('button', {class: 'chip', type: 'button', 'aria-pressed': String(isOn(val))}, label);
      b.onclick = () => { onClick(val); S.shown = 30; render(); };
      container.appendChild(b);
    });
  }

  const toggle = (set, v, all) => {
    if (set.size === all.length) { set.clear(); set.add(v); }           // primul click: doar acesta
    else if (set.has(v)) { set.delete(v); if (!set.size) all.forEach(x => set.add(x)); }
    else set.add(v);
  };

  function filtered() {
    return SD.combos.filter(c => S.origins.has(c.origin) && S.hubs.has(c.hub));
  }

  function renderCards() {
    const box = $('s-cards'); box.innerHTML = '';
    const rows = filtered();
    Object.keys(ORIGINS_MAP).filter(o => S.origins.has(o)).forEach(from => {
      const best = rows.filter(c => c.origin === from).sort((a, b) => price(a) - price(b))[0];
      const card = el('div', {class: 'card'});
      if (!best) { card.innerHTML = `<div class="country">${ORIGIN_NAME(from)}</div><p class="empty">Nicio combinație cu filtrele actuale.</p>`; box.appendChild(card); return; }
      const direct = DIRECT_BEST[from];
      const diff = direct ? direct - price(best) : null;
      card.innerHTML = `<div class="country"><span>${ORIGIN_NAME(from)}</span></div>
        <div class="price">${fmtEUR(price(best))}</div>
        <div class="pp">total 4 persoane${S.bags && best.bags ? ` · incl. ~${fmtEUR(best.bags)} bagaje` : ''}</div>
        ${diff != null ? (diff > 0 ? `<div class="save">cu ${fmtEUR(diff)} mai ieftin decât cel mai bun bilet întreg</div>` : `<div class="pp">bilet întreg cel mai ieftin: ${fmtEUR(direct)}</div>`) : ''}
        <div class="det"><b>prin ${hubName(best.hub)}</b></div>
        <div class="det"><b>${fmtDate(best.depart)}</b> → acasă <b>${fmtDate(best.home)}</b></div>
        <div class="det">${nightsTxt(best.stop_out)} în ${hubName(best.hub)} · aterizare ${best.dest} <b>${fmtDate(best.legs[1].arrival_date)}</b>, retur <b>${fmtDate(best.legs[1].return_date)}</b> (${best.nights} nopți de cazare)</div>
        <div><span class="bag manual">🖐️ Muți bagajele singur</span></div>
        <a class="btn" href="#c-${SD.combos.indexOf(best)}">Vezi itinerariul ↓</a>`;
      card.querySelector('a.btn').onclick = e => {
        S.hubs = new Set([best.hub]); render();
        setTimeout(() => document.getElementById('c-' + SD.combos.indexOf(best))?.scrollIntoView({behavior: 'smooth', block: 'center'}), 50);
        e.preventDefault();
      };
      box.appendChild(card);
    });
  }

  function renderHubTable() {
    const t = $('s-hubs');
    const origins = Object.keys(ORIGINS_MAP).filter(o => S.origins.has(o));
    const rows = SD.combos.filter(c => S.origins.has(c.origin));
    const best = {};
    rows.forEach(c => { const k = c.hub + '|' + c.origin; if (!best[k] || price(c) < price(best[k])) best[k] = c; });
    const prices = Object.values(best).map(price);
    const min = Math.min(...prices), max = Math.max(...prices);
    const lowest = h => Math.min(...origins.map(o => best[h + '|' + o] ? price(best[h + '|' + o]) : 1e9));
    const hubs = Object.keys(SD.hubs).filter(h => origins.some(o => best[h + '|' + o])).sort((a, b) => lowest(a) - lowest(b));
    let h = '<thead><tr><th>Oprire în</th>' + origins.map(o => `<th style="text-align:center">din ${ORIGIN_NAME(o)}</th>`).join('') + '</tr></thead><tbody>';
    hubs.forEach(hub => {
      h += `<tr><td>${hubName(hub)}</td>`;
      origins.forEach(o => {
        const c = best[hub + '|' + o];
        h += c ? `<td class="cell ${heatClass(price(c), min, max)}"><a href="#" data-hub="${hub}" data-origin="${o}">${fmtEUR(price(c))}<small>plecare ${fmtDate(c.depart)}</small></a></td>`
               : `<td class="cell"><a style="color:var(--muted);font-weight:400">—</a></td>`;
      });
      h += '</tr>';
    });
    t.innerHTML = h + '</tbody>';
    t.querySelectorAll('a[data-hub]').forEach(a => a.onclick = e => {
      e.preventDefault(); S.hubs = new Set([a.dataset.hub]); S.origins = new Set([a.dataset.origin]); S.shown = 30; render();
      $('s-list').scrollIntoView({behavior: 'smooth'});
    });
  }

  function legHtml(l, label) {
    const extra = l.low_cost ? `<small>low-cost: fără bagaj de cală${S.bags ? ` (+~${fmtEUR(l.bag_fee)} estimat)` : ''}</small>` : '';
    return `<div class="lg">
      <div class="d">${fmtDate(l.date)}${l.return_date ? ' → ' + fmtDate(l.return_date) : ''}</div>
      <div class="what"><b>${label}</b> · ${l.airlines || '—'}<small>${fmtDur(l.duration_min)} · ${stopsTxt(l.stops)}${l.bag_transfer === 'verify' ? ' · <span class="bag manual">escală cu transfer nesigur</span>' : ''}${l.departure ? ' · pleacă ' + l.departure.split(' on ')[0] : ''}</small>${extra}</div>
      <div class="p">${fmtEUR(l.price)}<a href="${l.link}" target="_blank" rel="noopener">Google Flights ↗</a></div>
    </div>`;
  }

  function renderList() {
    const rows = filtered().sort((a, b) => price(a) - price(b));
    $('s-count').textContent = rows.length + ' combinații';
    const list = $('s-list');
    if (!rows.length) { list.innerHTML = '<p class="empty">Nicio combinație pentru filtrele alese.</p>'; $('s-more').innerHTML = ''; return; }
    list.innerHTML = rows.slice(0, S.shown).map(c => {
      const [a, b, r] = c.legs;
      const direct = DIRECT_BEST[c.origin];
      const diff = direct ? direct - price(c) : null;
      return `<article class="combo" id="c-${SD.combos.indexOf(c)}">
        <div class="combo-head">
          <div><div class="route">${ORIGIN_NAME(c.origin)} → ${hubName(c.hub)} → ${c.country} (${c.dest})</div>
            <div class="pp">${fmtDate(c.depart)} – ${fmtDate(c.home)} · ${c.nights} nopți de cazare la destinație${diff > 0 ? ` · <span class="save">−${fmtEUR(diff)} față de bilet întreg</span>` : ''}</div></div>
          <div class="tot"><span class="bag manual">🖐️ 2 transferuri manuale</span> ${fmtEUR(price(c))}<small>${S.bags && c.bags ? `bilete ${fmtEUR(c.tickets)} + bagaje ~${fmtEUR(c.bags)}` : 'total 4 persoane'}</small></div>
        </div>
        <div class="legs">
          ${legHtml(a, `${a.origin} → ${hubName(c.hub)}`)}
          <div class="stay">🏙️ <b>${nightsTxt(c.stop_out)}</b> în ${hubName(c.hub)} · 🖐️ ridici bagajele și le predai din nou</div>
          ${legHtml(b, `${hubName(c.hub)} ⇄ ${c.dest} dus-întors`)}
          <div class="stay">🏝️ aterizare <b>${fmtDate(b.arrival_date)}</b>, retur <b>${fmtDate(b.return_date)}</b>: <b>${c.nights} nopți de cazare</b></div>
          <div class="stay">🏙️ înapoi în ${hubName(c.hub)}, zbor spre casă după <b>${c.stop_ret} zile</b> de la plecarea din ${c.dest} · 🖐️ ridici bagajele și le predai din nou</div>
          ${legHtml(r, `${hubName(c.hub)} → ${r.to}`)}
        </div>
      </article>`;
    }).join('');
    $('s-more').innerHTML = rows.length > S.shown ? `<button class="chip" type="button">Arată mai multe (${rows.length - S.shown})</button>` : '';
    const more = $('s-more').querySelector('button');
    if (more) more.onclick = () => { S.shown += 30; renderList(); };
  }

  function renderCompare() {
    const manual = {};
    SD.combos.forEach(c => { if (!manual[c.origin] || c.total < manual[c.origin].total) manual[c.origin] = c; });
    const open = tab => `document.querySelector('.tab[data-tab=${tab}]').click()`;
    $('compare').innerHTML = `<thead><tr><th>Plecare din</th><th>🧳 Automat (un bilet)</th><th>🖐️ Manual (cu oprire)</th></tr></thead><tbody>` +
      Object.keys(ORIGINS_MAP).map(o => {
        const a = DIRECT_BEST[o], m = manual[o];
        return `<tr><td>${ORIGIN_NAME(o)}</td>
          <td>${a ? `<a href="#" onclick="${open('direct')};return false">${fmtEUR(a)}</a>` : '—'}</td>
          <td>${m ? `<a href="#" onclick="${open('stop')};return false">${fmtEUR(m.total)}</a><small>prin ${hubName(m.hub)}, cu bagaje estimate</small>` : '—'}</td></tr>`;
      }).join('') + '</tbody>';
    $('compare-box').hidden = false;
  }

  function render() {
    const origins = Object.keys(ORIGINS_MAP);
    const hubs = Object.keys(SD.hubs).filter(h => SD.combos.some(c => c.hub === h));
    chips($('s-origin'), origins.map(o => [o, ORIGINS_MAP[o]]), v => S.origins.has(v), v => toggle(S.origins, v, origins));
    chips($('s-hub'), [['*', 'Toate'], ...hubs.map(h => [h, hubName(h)])], v => v === '*' ? S.hubs.size === hubs.length : S.hubs.size !== hubs.length && S.hubs.has(v),
      v => v === '*' ? (S.hubs = new Set(hubs)) : toggle(S.hubs, v, hubs));
    chips($('s-bags'), [[true, 'Cu bagaje (estimat)'], [false, 'Doar bilete']], v => S.bags === v, v => S.bags = v);
    renderCards(); renderHubTable(); renderList();
  }

  let ORIGINS_MAP = {TSR: 'Timișoara', CLJ: 'Cluj-Napoca', BUD: 'Budapesta', BEG: 'Belgrad'};
  const ORIGIN_NAME = o => ORIGINS_MAP[o] || o;

  Promise.all([
    fetch('data/stopovers.json', {cache: 'no-store'}).then(r => r.json()),
    fetch('data/results.json', {cache: 'no-store'}).then(r => r.json()).catch(() => null),
  ]).then(([sd, direct]) => {
    // Datele scanate după regulile vechi nu se mai afișează.
    if (!sd.max_stops) { $('s-cards').innerHTML = UPDATING; return; }
    SD = sd;
    $('s-bagfee').textContent = sd.bag_fee_per_leg;
    if (direct) {
      ORIGINS_MAP = direct.origins;
      if (direct.max_stops) direct.results.forEach(r => { const o = r.options.find(x => x.bag_transfer === 'auto'); if (o && (!DIRECT_BEST[r.origin] || o.price < DIRECT_BEST[r.origin])) DIRECT_BEST[r.origin] = o.price; });
    }
    S.origins = new Set(Object.keys(ORIGINS_MAP));
    S.hubs = new Set(Object.keys(sd.hubs).filter(h => sd.combos.some(c => c.hub === h)));
    render();
    renderCompare();
  }).catch(() => { $('s-cards').innerHTML = '<p class="empty">Încă nu există combinații. Prima scanare rulează în curând.</p>'; });
})();
