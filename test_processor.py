
from app.services.data_processor import process_feedback_file

file_path = "data/sample/sample_feedback.csv"

result = process_feedback_file(
    file_path,
    feedback_column="Feedback",
    source_id_column="Customer_ID"
)

print("\nPROCESSED CUSTOMER FEEDBACK\n")

print(
    result[
        [
            "record_id",
            "source_id",
            "original_feedback",
            "is_duplicate",
            "duplicate_of_record_id",
        ]
    ].to_string(index=False)
)

print("\nSUMMARY\n")

print("Total valid records:", len(result))
print("Duplicate records:", result["is_duplicate"].sum())
print("Unique feedback records:", (~result["is_duplicate"]).sum())
