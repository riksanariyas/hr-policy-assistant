from src import auth

DEMO_USERS = [
    ("admin", "Admin@123", "admin"),
    ("employee1", "Employee@123", "employee"),
    ("employee2", "Employee@456", "employee"),
]


def seed_demo_users():
    for username, password, role in DEMO_USERS:
        try:
            auth.create_user(username, password, role)
            print(f"Created {role}: {username}")
        except ValueError as e:
            print("Skipped:", e)


if __name__ == "__main__":
    seed_demo_users()