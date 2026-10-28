-- Separate database used by the automated test suite.
CREATE DATABASE IF NOT EXISTS ledger_test;
GRANT ALL PRIVILEGES ON ledger_test.* TO 'ledger'@'%';
FLUSH PRIVILEGES;
