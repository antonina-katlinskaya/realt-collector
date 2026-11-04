/**
 * Independent Realt collector wake-up for Cloudflare Workers.
 * The existing GitHub workflow retains the authoritative due/cooldown/budget
 * decisions. This worker only requests an ordinary workflow_dispatch.
 * No cron trigger should be enabled until REALT_GITHUB_TOKEN is installed.
 */
const REPOSITORY = 'antonina-katlinskaya/realt-collector';
const WORKFLOW = 'collect.yml';

async function wakeCollector(env) {
  const token = env.REALT_GITHUB_TOKEN;
  if (typeof token !== 'string' || token.trim().length === 0) {
    throw new Error('REALT_GITHUB_TOKEN is not configured; no dispatch was attempted');
  }
  const endpoint = 'https://api.github.com/repos/' + REPOSITORY + '/actions/workflows/' + WORKFLOW + '/dispatches';
  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
      'User-Agent': 'realt-collector-cloudflare-wakeup',
    },
    body: JSON.stringify({ref: 'main'}),
  });
  if (response.status !== 204) {
    throw new Error('Realt collector dispatch was not accepted (HTTP ' + response.status + ')');
  }
  console.log('Realt collector dispatch accepted by GitHub');
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === 'GET' && url.pathname === '/health') {
      return Response.json({service: 'realt-collector-external-wakeup', ok: true});
    }
    return new Response('Not found', {status: 404});
  },
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(wakeCollector(env));
  },
};
