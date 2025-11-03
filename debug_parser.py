#!/usr/bin/env python3
"""Debug script to check CSV parsing."""

import pandas as pd

csv_path = "assets/Quiz 3 - Divide and Conquer Student Analysis Report.csv"
df = pd.read_csv(csv_path)

print("DataFrame shape:", df.shape)
print(f"\nFirst student: {df.iloc[0]['Name']}")

# Check all Status columns for first student
status_cols = [col for col in df.columns if col.startswith('Status')]
print(f"\nFound {len(status_cols)} Status columns")

print("\nChecking which questions were graded for first student:")
for i, col in enumerate(df.columns):
    if col.startswith('Status'):
        status = df.iloc[0][col]
        if status == 'Graded':
            # Find the ItemType and answer columns before this Status
            # Pattern: ItemID, ItemType, Question, EarnedPoints, Status
            col_idx = df.columns.get_loc(col)
            item_type_idx = col_idx - 3
            question_idx = col_idx - 2
            answer_idx = col_idx - 2
            
            item_type = df.iloc[0].iloc[item_type_idx]
            question_header = df.columns[question_idx]
            answer = df.iloc[0].iloc[answer_idx]
            
            print(f"\n  Status column: {col} (index {col_idx})")
            print(f"  ItemType: {item_type}")
            print(f"  Question header: {question_header[:80]}...")
            print(f"  Answer: {str(answer)[:100]}...")
