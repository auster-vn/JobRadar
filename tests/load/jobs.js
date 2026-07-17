import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";

const jobsLatency = new Trend("jobs_latency", true);
const baseUrl = __ENV.BASE_URL?.replace(/\/$/, "");

if (!baseUrl) {
  throw new Error(
    "BASE_URL is required and must point to an isolated API with rate limiting disabled",
  );
}

export const options = {
  scenarios: {
    jobs: {
      executor: "constant-arrival-rate",
      rate: 100,
      timeUnit: "1s",
      duration: "60s",
      preAllocatedVUs: 30,
      maxVUs: 150,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    jobs_latency: ["p(95)<500"],
  },
};

export default function () {
  const response = http.get(`${baseUrl}/api/jobs?limit=20`);
  jobsLatency.add(response.timings.duration);
  check(response, { "jobs returned": (result) => result.status === 200 });
}
