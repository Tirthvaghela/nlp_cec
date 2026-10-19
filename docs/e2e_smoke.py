"""End-to-end UI smoke test of the full workflow, driven through the browser.

Teacher creates an assessment + question with a rubric and publishes it -> a student
saves a draft and submits -> the teacher evaluates with the NLP engine, adjusts one
mark with a reason and publishes -> the student opens the published result.

Prerequisites: backend (:8000) + frontend dev server (:5173) running and seed data loaded
(`python -m scripts.seed --reset`). This script WRITES data; re-seed afterwards for a clean demo.
    pip install playwright==1.55.0
    python docs/e2e_smoke.py
"""

from __future__ import annotations

import os
import re
import sys
import time

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("AW_BASE_URL", "http://localhost:5173")  # override to target an isolated stack
TITLE = f"E2E check {int(time.time())}"
errors: list[str] = []


def login(page, email, password):
    page.goto(f"{BASE}/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password", exact=True).fill(password)
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(re.compile(r"/(teacher|student)$"))


def step(msg):
    print("-", msg)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)

        # --- teacher builds and publishes an assessment -----------------------------
        t = browser.new_context(viewport={"width": 1366, "height": 900}).new_page()
        t.on("pageerror", lambda e: errors.append(str(e)))
        login(t, "teacher@answerwise.dev", "Teacher@123")
        t.get_by_role("link", name="New assessment").click()
        t.get_by_label("Title").fill(TITLE)
        t.get_by_label("Subject").fill("Natural Language Processing")
        t.get_by_label("Instructions to students").fill("Answer in full sentences.")
        t.get_by_role("button", name="Create assessment").click()
        t.wait_for_url(re.compile(r"/teacher/assessments/[0-9a-f]{24}$"))
        assessment_url = t.url
        step("assessment created")

        # a new assessment opens the editor with an empty "new question" panel
        t.get_by_label("Question text").fill("What are stop words? When should stop-word removal be avoided?")
        t.get_by_label("Maximum marks").fill("3")
        t.get_by_label("Reference answer").fill("Stop words are very frequent words like the and is that carry little meaning. "
                                                "Removing them reduces noise. They should be kept when they carry meaning, such as 'not' in sentiment analysis.")
        concepts = [
            ("Definition", "Stop words are very frequent function words such as the and is that carry little meaning", "1"),
            ("Benefit of removal", "Removing stop words reduces noise and data size and makes search and classification more efficient", "1"),
            ("When to keep them", "Stop words should be kept when they carry meaning such as negations like not in sentiment analysis", "1"),
        ]
        t.get_by_role("button", name="Add concept").click()  # 2 default rows + 1
        for i, (label, desc, marks) in enumerate(concepts):
            t.get_by_label(f"Concept {i + 1} name").fill(label)
            t.get_by_label(f"Concept {i + 1}: what counts as covered").fill(desc)
            t.get_by_label(f"Concept {i + 1} marks").fill(marks)
        expect(t.get_by_text("3 of 3 marks allocated")).to_be_visible()
        t.get_by_role("button", name="Save question").click()
        t.wait_for_url(re.compile(r"/questions/[0-9a-f]{24}$"))
        step("question + rubric saved")

        t.get_by_text("Test the rubric").click()
        t.get_by_label("Sample answer").fill("Stop words like 'the' carry little meaning, but keep 'not' for sentiment analysis.")
        t.get_by_role("button", name="Run NLP evaluation").click()
        expect(t.get_by_text("AI-suggested score")).to_be_visible(timeout=30000)
        step("rubric sandbox evaluated a sample answer")

        t.goto(assessment_url)
        t.get_by_role("button", name="Publish to students").click()
        t.get_by_role("alertdialog").get_by_role("button", name="Publish").click()
        expect(t.get_by_text("Assessment published")).to_be_visible()
        step("assessment published")

        # --- student drafts and submits --------------------------------------------
        s = browser.new_context(viewport={"width": 1366, "height": 900}).new_page()
        s.on("pageerror", lambda e: errors.append(str(e)))
        login(s, "riya@answerwise.dev", "Student@123")
        s.goto(f"{BASE}/student/assessments")
        expect(s.get_by_text(TITLE)).to_be_visible()  # the newly published assessment is listed
        s.goto(f"{BASE}/student/assessments/{assessment_url.rsplit('/', 1)[-1]}")
        s.wait_for_url(re.compile(r"/student/assessments/[0-9a-f]{24}$"))
        box = s.get_by_role("textbox")
        box.fill("Stop words are common words such as the, is and and that add little meaning. "
                 "Removing them makes text classification faster and reduces noise.")
        s.get_by_role("button", name="Save draft").click()
        expect(s.get_by_text(re.compile("Draft saved at"))).to_be_visible()
        step("student draft saved")
        s.get_by_role("button", name="Submit assessment").click()
        s.get_by_role("alertdialog").get_by_role("button", name="Submit answers").click()
        expect(s.get_by_text("Submission received")).to_be_visible()
        step("student submitted")

        # --- teacher evaluates, adjusts and publishes ------------------------------
        t.goto(assessment_url + "?tab=submissions")
        t.get_by_role("link", name="Evaluate").first.click()
        t.wait_for_url(re.compile(r"/teacher/submissions/\w+"))
        t.get_by_role("button", name="Run NLP evaluation").click()
        expect(t.get_by_text("AI-suggested score")).to_be_visible(timeout=60000)
        ai = re.search(r"AI ([\d.]+) /", t.get_by_role("tab").first.inner_text()).group(1)
        step(f"NLP evaluation done (AI-suggested {ai}/3)")
        new_score = "2.5" if ai != "2.5" else "2"
        t.get_by_label("Final score").fill(new_score)
        t.get_by_role("button", name="Save final score").click()
        expect(t.get_by_text("Give a short reason")).to_be_visible()
        t.get_by_label("Reason for adjustment").fill("Explanation of benefits was adequate.")
        t.get_by_label("Comment to student").fill("Good - also explain when to keep stop words.")
        t.get_by_role("button", name="Save final score").click()
        expect(t.get_by_text("Review saved.")).to_be_visible()
        step(f"teacher adjusted mark to {new_score} with a reason")
        t.get_by_role("button", name="Publish result").click()
        t.get_by_role("alertdialog").get_by_role("button", name="Publish result").click()
        expect(t.get_by_text("Result published.")).to_be_visible()
        step("result published")

        # --- student sees the result ----------------------------------------------
        s.goto(f"{BASE}/student/results")
        s.get_by_role("row").filter(has_text=TITLE).get_by_role("link", name="View feedback").click()
        expect(s.get_by_text(re.compile(r"Teacher adjusted \(AI suggested [\d.]+\)"))).to_be_visible()
        expect(s.get_by_text("Good - also explain when to keep stop words.")).to_be_visible()
        step("student sees final mark, AI suggestion note, concept feedback and teacher comment")
        browser.close()

    if errors:
        print("BROWSER ERRORS:", *errors, sep="\n  ")
        sys.exit(1)
    print("E2E workflow passed")


if __name__ == "__main__":
    main()
