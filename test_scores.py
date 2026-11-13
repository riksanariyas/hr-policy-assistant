import csv

from src import store

with open("tests/test_questions.csv", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        best = store.search(row["question"], k=3)[0]
        print(f'{row["id"]:>2} {row["category"]:<8} {best["score"]}  {best["source"]} - {best["section"]}')
        print(f'      expected: {row["expected_source"]}')