# Generate a JWT secret without OpenSSL.
python -c "import secrets; print(secrets.token_hex(32))"
