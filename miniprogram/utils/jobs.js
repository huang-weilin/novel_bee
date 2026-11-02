const api = require("./api");

const DEFAULT_INTERVAL = 1500;
const DEFAULT_TIMEOUT = 10 * 60 * 1000;

function waitForJob(jobId, options) {
  const opts = options || {};
  const interval = opts.interval || DEFAULT_INTERVAL;
  const timeout = opts.timeout || DEFAULT_TIMEOUT;
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    function poll() {
      api
        .getJob(jobId)
        .then((job) => {
          if (opts.onUpdate) opts.onUpdate(job);
          if (job.status === "queued" || job.status === "running") {
            if (Date.now() - startedAt > timeout) {
              reject(new Error("等待超时；任务可能仍在后台运行，可稍后刷新。"));
              return;
            }
            setTimeout(poll, interval);
            return;
          }
          resolve(job);
        })
        .catch(reject);
    }
    poll();
  });
}

module.exports = { waitForJob };
