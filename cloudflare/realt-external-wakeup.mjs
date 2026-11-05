/**
 * Independent Realt wake-up without consuming a Cloudflare Cron Trigger slot.
 * The existing GitHub collector retains its due/cooldown/budget decisions.
 */
import { DurableObject } from 'cloudflare:workers';

const REPOSITORY = 'antonina-katlinskaya/realt-collector';
const WORKFLOW = 'collect.yml';

function nextWakeAfter(afterMs) {
  const first = Math.ceil((afterMs + 1000) / 60000) * 60000;
  for (let minuteOffset = 0; minuteOffset <= 1440; minuteOffset++) {
    const timestamp = first + minuteOffset * 60000;
    const date = new Date(timestamp);
    const hour = date.getUTCHours();
    const minute = date.getUTCMinutes();
    if (hour >= 4 && hour <= 18 && (minute === 7 || minute === 37)) return timestamp;
  }
  throw new Error('Next Realt alarm was not found');
}

async function wakeCollector(env) {
  const token = env.REALT_GITHUB_TOKEN;
  if (typeof token !== 'string' || token.trim().length === 0) {
    throw new Error('REALT_GITHUB_TOKEN is not configured');
  }
  const endpoint = 'https://api.github.com/repos/' + REPOSITORY +
    '/actions/workflows/' + WORKFLOW + '/dispatches';
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
      'User-Agent': 'realt-collector-cloudflare-wakeup',
    },
    body: JSON.stringify({ ref: 'main' }),
  });
  if (response.status !== 204) {
    throw new Error('GitHub workflow dispatch returned HTTP ' + response.status);
  }
  console.log('GitHub accepted Realt collector wake-up');
}

export class RealtWakeAlarm extends DurableObject {
  async ensureArmed() {
    let next = await this.ctx.storage.getAlarm();
    if (next === null) {
      // Bootstrap only once. The first wake-up validates GitHub permissions.
      next = Date.now() + 5000;
      await this.ctx.storage.setAlarm(next);
    }
    const last = (await this.ctx.storage.get('lastStatus')) ?? null;
    return { armed: true, nextAlarmAt: new Date(next).toISOString(), last };
  }

  async alarm() {
    // Save the next wake-up before calling GitHub, to survive upstream outages.
    await this.ctx.storage.setAlarm(nextWakeAfter(Date.now()));
    const checkedAt = new Date().toISOString();
    try {
      await wakeCollector(this.env);
      await this.ctx.storage.put('lastStatus', { checkedAt, accepted: true });
    } catch (error) {
      const message = String(error?.message ?? error).slice(0, 160);
      await this.ctx.storage.put('lastStatus', {
        checkedAt, accepted: false, error: message
      });
      console.error('Realt alarm failed:', message);
    }
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/health') {
      const status = await env.REALT_WAKE_ALARM.getByName('realt-main').ensureArmed();
      return Response.json({
        service: 'realt-collector-external-wakeup',
        ok: true,
        ...status
      });
    }
    return new Response('Not found', { status: 404 });
  },

  async scheduled(_controller, env, ctx) {
    // Retain compatibility if a Cron Trigger is added later.
    ctx.waitUntil(wakeCollector(env));
  },
};
