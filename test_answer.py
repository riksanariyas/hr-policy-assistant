import csv
import time

from src.answer import answer_question

with open("tests/test_questions.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        result = answer_question(row["question"])
        print(f'\n#{row["id"]} [{row["category"]}] {row["question"]}')
        print("   ANSWER:", result["answer"].replace("\n", " | ")[:300])
        print("   SOURCES:", result["sources"][:3])
        print("   EXPECTED:", row["expected_answer"])
        time.sleep(2)  # be gentle with the free tier