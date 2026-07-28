from getpass import getpass

from werkzeug.security import generate_password_hash


def main() -> None:
    password = getpass("Admin password: ")
    confirmation = getpass("Confirm admin password: ")
    if not password:
        raise SystemExit("Admin password cannot be empty.")
    if password != confirmation:
        raise SystemExit("Passwords do not match.")
    print(generate_password_hash(password))


if __name__ == "__main__":
    main()
