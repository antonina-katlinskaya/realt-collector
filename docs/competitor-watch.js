'use strict';

async function loadCompetitorWatch() {
  const status = document.getElementById('competitor-watch-status');
  const tables = document.getElementById('competitor-watch-tables');
  const response = await fetch('https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/docs/competitor-watch.json', {cache: 'no-store'});
  if (!response.ok) throw new Error('Watch data unavailable');
  const {updatedAt, rows} = await response.json();
  const format = new Intl.DateTimeFormat('ru-RU', {timeZone: 'Europe/Minsk', dateStyle: 'short', timeStyle: 'short'});
  status.textContent = 'Последний срез · ' + format.format(new Date(updatedAt)) + ' (Минск)';
  for (const complex of new Set(rows.map(row => row.complex))) {
    const heading = document.createElement('h3');
    heading.textContent = complex;
    const table = document.createElement('table');
    const head = table.createTHead().insertRow();
    for (const label of ['Автор или агентство', 'Карточек', 'Дней размещения', 'Последняя карточка']) {
      const cell = document.createElement('th');
      cell.scope = 'col';
      cell.textContent = label;
      head.append(cell);
    }
    const body = table.createTBody();
    for (const item of rows.filter(row => row.complex === complex).sort((a, b) => b.count - a.count || b.days - a.days)) {
      const row = body.insertRow();
      for (const value of [item.label, item.count, item.days]) row.insertCell().textContent = value;
      const cell = row.insertCell();
      cell.textContent = '—';
      if (item.code && item.last) {
        const link = document.createElement('a');
        link.href = 'https://realt.by/sale-flats/object/' + encodeURIComponent(item.code) + '/';
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = format.format(new Date(item.last));
        cell.replaceChildren(link);
      }
    }
    const wrap = document.createElement('div');
    wrap.style.overflowX = 'auto';
    wrap.append(table);
    tables.append(heading, wrap);
  }
}

loadCompetitorWatch().catch(() => {
  document.getElementById('competitor-watch-status').textContent = 'Срез конкурентов временно недоступен.';
});
