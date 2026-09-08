"""Load test for the public status endpoint - the only route that can be
hit without auth, and the one most likely to see real traffic.

Deliberately not load-testing the evaluation pipeline: that's bounded by
Gemini's/OpenAI's rate limits and costs real money per request, so
hammering it would measure their infrastructure and bill you for the
privilege.
"""
from locust import HttpUser, task, between


class StatusPageUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def status(self):
        self.client.get("/api/v1/status")

    @task(1)
    def health(self):
        self.client.get("/health")