// Tab-ul „Cu oprire 1–2 zile”: combinații cu bilete separate printr-un oraș-hub.
(() => {
  const S = {country: 'Toate', origins: new Set(), hubs: null, bags: true, shown: 30, month: '*'};
  let SD, DIRECT_BEST = {}, DIRECT_FROM = {};

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

  function filtered(allCountries = false) {
    return SD.combos.filter(c =>
      (allCountries || S.country === 'Toate' || c.country === S.country) &&
      S.origins.has(c.origin) && S.hubs.has(c.hub) && (S.month === '*' || c.depart.startsWith(S.month)));
  }

  function renderCards() {
    const box = $('s-cards'); box.innerHTML = '';
    const rows = filtered(true);
    COUNTRIES.forEach(country => {
      const best = rows.filter(c => c.country === country).sort((a, b) => price(a) - price(b))[0];
      const card = el('div', {class: 'card'});
      if (!best) { card.innerHTML = `<div class="country">${FLAG[country]} ${country}</div><p class="empty">Nicio combinație cu filtrele actuale.</p>`; box.appendChild(card); return; }
      const direct = DIRECT_BEST[country];
      const diff = direct ? direct - price(best) : null;
      card.innerHTML = `<div class="country"><span>${FLAG[country]} ${country}</span></div>
        <div class="price">${fmtEUR(price(best))}</div>
        <div class="pp">total 4 persoane${S.bags && best.bags ? ` · incl. ~${fmtEUR(best.bags)} bagaje` : ''}</div>
        ${diff != null ? (diff > 0 ? `<div class="save">cu ${fmtEUR(diff)} mai ieftin decât cel mai bun bilet întreg</div>` : `<div class="pp">bilet întreg cel mai ieftin: ${fmtEUR(direct)}</div>`) : ''}
        <div class="det"><b>${ORIGIN_NAME(best.origin)}</b> → <b>${hubName(best.hub)}</b> → ${best.dest}</div>
        <div class="det"><b>${fmtDate(best.depart)}</b> → acasă <b>${fmtDate(best.home)}</b></div>
        <div class="det">${nightsTxt(best.stop_out)} în ${hubName(best.hub)} · aterizare ${best.dest} <b>${fmtDate(best.legs[1].arrival_date)}</b>, retur <b>${fmtDate(best.legs[1].return_date)}</b> (${best.nights} nopți de cazare)</div>
        <div><span class="bag manual">🖐️ Muți bagajele singur</span></div>
        <a class="btn" href="#c-${SD.combos.indexOf(best)}">Vezi itinerariul ↓</a>`;
      card.querySelector('a.btn').onclick = e => {
        S.country = country; S.hubs = new Set([best.hub]); render();
        setTimeout(() => document.getElementById('c-' + SD.combos.indexOf(best))?.scrollIntoView({behavior: 'smooth', block: 'center'}), 50);
        e.preventDefault();
      };
      box.appendChild(card);
    });
  }

  function renderHubTable() {
    const t = $('s-hubs');
    const rows = SD.combos.filter(c => S.origins.has(c.origin));
    const best = {};
    rows.forEach(c => { const k = c.hub + '|' + c.country; if (!best[k] || price(c) < price(best[k])) best[k] = c; });
    const prices = Object.values(best).map(price);
    const min = Math.min(...prices), max = Math.max(...prices);
    const hubs = Object.keys(SD.hubs).filter(h => COUNTRIES.some(c => best[h + '|' + c]))
      .sort((a, b) => Math.min(...COUNTRIES.map(c => best[a + '|' + c] ? price(best[a + '|' + c]) : 1e9)) - Math.min(...COUNTRIES.map(c => best[b + '|' + c] ? price(best[b + '|' + c]) : 1e9)));
    let h = '<thead><tr><th>Oprire în</th>' + COUNTRIES.map(c => `<th style="text-align:center">${FLAG[c]} ${c}</th>`).join('') + '</tr></thead><tbody>';
    hubs.forEach(hub => {
      h += `<tr><td>${hubName(hub)}</td>`;
      COUNTRIES.forEach(country => {
        const c = best[hub + '|' + country];
        h += c ? `<td class="cell ${heatClass(price(c), min, max)}"><a href="#" data-hub="${hub}" data-country="${country}">${fmtEUR(price(c))}<small>din ${c.origin} · ${fmtDate(c.depart)}</small></a></td>`
               : `<td class="cell"><a style="color:var(--muted);font-weight:400">—</a></td>`;
      });
      h += '</tr>';
    });
    t.innerHTML = h + '</tbody>';
    t.querySelectorAll('a[data-hub]').forEach(a => a.onclick = e => {
      e.preventDefault(); S.hubs = new Set([a.dataset.hub]); S.country = a.dataset.country; S.shown = 30; render();
      $('s-list').scrollIntoView({behavior: 'smooth'});
    });
  }

  function legHtml(l, label) {
    const extra = l.low_cost ? `<small>low-cost: fără bagaj de cală${S.bags ? ` (+~${fmtEUR(l.bag_fee)} estimat)` : ''}</small>` : '';
    return `<div class="lg">
      <div class="d">${fmtDate(l.date)}${l.return_date ? ' → ' + fmtDate(l.return_date) : ''}</div>
      <div class="what"><b>${label}</b><small>${l.return_flight ? '🛫 Tur: ' : ''}${flightTxt(l)}</small>${l.return_flight ? `<small>🛬 Retur: ${flightTxt(l.return_flight)}</small>` : ''}${l.bag_transfer === 'verify' ? '<small><span class="bag manual">escală cu transfer nesigur</span></small>' : ''}${extra}</div>
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
      const direct = DIRECT_BEST[c.country];
      const diff = direct ? direct - price(c) : null;
      return `<article class="combo" id="c-${SD.combos.indexOf(c)}">
        <div class="combo-head">
          <div><div class="route">${FLAG[c.country]} ${ORIGIN_NAME(c.origin)} → ${hubName(c.hub)} → ${c.country} (${c.dest})</div>
            <div class="pp">${fmtDate(c.depart)} – ${fmtDate(c.home)} · ${c.nights} nopți de cazare la destinație${diff > 0 ? ` · <span class="save">−${fmtEUR(diff)} față de bilet întreg</span>` : ''}</div></div>
          <div class="tot"><span class="bag manual">🖐️ 2 transferuri manuale</span> ${fmtEUR(price(c))}<small>${S.bags && c.bags ? `bilete ${fmtEUR(c.tickets)} + bagaje ~${fmtEUR(c.bags)}` : 'total 4 persoane'}</small></div>
        </div>
        <div class="legs">
          ${legHtml(a, `${a.origin} → ${hubName(c.hub)}`)}
          <div class="stay">🏙️ <b>${nightsTxt(c.stop_out)}</b> în ${hubName(c.hub)} · 🖐️ ridici bagajele și le predai din nou</div>
          ${legHtml(b, `${hubName(c.hub)} ⇄ ${c.dest} dus-întors`)}
          <div class="stay">🏝️ aterizare <b>${fmtDate(b.arrival_date)}</b>, retur <b>${fmtDate(b.return_date)}</b>: <b>${c.nights} nopți de cazare</b></div>
          <div class="stay">🏙️ aterizare în ${hubName(c.hub)} <b>${fmtDate(b.return_flight.arrival_date)}</b>, <b>${nightsTxt(c.stop_ret)}</b> acolo · 🖐️ ridici bagajele și le predai din nou</div>
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
    SD.combos.forEach(c => { if (!manual[c.country] || c.total < manual[c.country].total) manual[c.country] = c; });
    const open = tab => `document.querySelector('.tab[data-tab=${tab}]').click()`;
    $('compare').innerHTML = `<thead><tr><th>Destinație</th><th>🧳 Automat (un bilet)</th><th>🖐️ Manual (cu oprire)</th></tr></thead><tbody>` +
      COUNTRIES.map(c => {
        const a = DIRECT_BEST[c], m = manual[c];
        return `<tr><td>${FLAG[c]} ${c}</td>
          <td>${a ? `<a href="#" onclick="${open('direct')};return false">${fmtEUR(a)}</a><small>din ${ORIGIN_NAME(DIRECT_FROM[c])}</small>` : '—'}</td>
          <td>${m ? `<a href="#" onclick="${open('stop')};return false">${fmtEUR(m.total)}</a><small>din ${ORIGIN_NAME(m.origin)}, prin ${hubName(m.hub)}, cu bagaje estimate</small>` : '—'}</td></tr>`;
      }).join('') + '</tbody>';
    $('compare-box').hidden = false;
  }

  function render() {
    const origins = Object.keys(ORIGINS_MAP);
    const hubs = Object.keys(SD.hubs).filter(h => SD.combos.some(c => c.hub === h));
    chips($('s-country'), [['Toate', 'Toate'], ...COUNTRIES.map(c => [c, FLAG[c] + ' ' + c])], v => S.country === v, v => S.country = v);
    chips($('s-origin'), origins.map(o => [o, ORIGINS_MAP[o]]), v => S.origins.has(v), v => toggle(S.origins, v, origins));
    chips($('s-month'), monthChips(SD.combos.map(c => c.depart)), v => S.month === v, v => S.month = v);
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
    if (!sd.return_checked) { $('s-cards').innerHTML = UPDATING; return; }
    SD = sd;
    $('s-bagfee').textContent = sd.bag_fee_per_leg;
    if (direct) {
      ORIGINS_MAP = direct.origins;
      if (direct.return_checked) direct.results.forEach(r => { const o = r.options.find(x => x.bag_transfer === 'auto'); if (o && (!DIRECT_BEST[r.country] || o.price < DIRECT_BEST[r.country])) { DIRECT_BEST[r.country] = o.price; DIRECT_FROM[r.country] = r.origin; } });
    }
    S.origins = new Set(Object.keys(ORIGINS_MAP));
    S.hubs = new Set(Object.keys(sd.hubs).filter(h => sd.combos.some(c => c.hub === h)));
    render();
    renderCompare();
  }).catch(() => { $('s-cards').innerHTML = '<p class="empty">Încă nu există combinații. Prima scanare rulează în curând.</p>'; });
})();
