# DBS302
## Practical 6 – Part A Report
### Securing Redis: Authentication, ACL, and TLS Encryption

---

## 1. Aim

To configure and test authentication, Access Control Lists (ACL), and TLS encryption on a Redis server running on a local Linux environment.

---

## 2. Objectives

- Confirm Redis is installed and running on the local machine.
- Disable the default open user and create separate ACL users with different permission levels.
- Test that each user can only access what they are allowed to, and nothing more.
- Generate self-signed TLS certificates using OpenSSL.
- Configure Redis to accept only TLS-encrypted connections.
- Connect to Redis over TLS and verify that plain-text connections are rejected.

---

## 3. Introduction

Redis is an in-memory data store commonly used for caching, session management, and message brokering. By default, Redis does not require any authentication, which means any client that can reach the server's port can read or modify all data. This is acceptable in a closed private network but becomes a serious risk in any environment where the server is reachable from multiple machines or over the internet.

To address this, Redis introduced Access Control Lists (ACL) starting from version 6. ACLs allow administrators to define multiple users, each with their own password, a list of commands they are allowed to run, and a pattern of key names they can access. This makes it possible to apply the principle of least privilege — each user or application gets only the minimum access it needs.

Beyond authentication, data travelling between the Redis client and server over a network can be intercepted and read if it is not encrypted. Transport Layer Security (TLS) solves this by encrypting the connection. In this practical, self-signed certificates were generated using OpenSSL to simulate how TLS would be set up in a real environment.

---

## 4. Procedure

### 4.1 Confirming Redis is Installed

```bash
redis-server --version
```
![alt text](images/1.png)

Redis was then started and a basic connectivity test was performed:

```bash
redis-server
redis-cli ping
```
![alt text](images/2.png)
![alt text](images/3.png)

A response of `PONG` confirmed the server was running and accepting connections.

---

### 4.2 Backing Up the Default Configuration

To avoid permanently breaking the default setup, the original configuration file was backed up before making any changes:

```bash
sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.backup
```
![alt text](images/4.png)

---

### 4.3 Configuring ACL Users in redis.conf

The Redis configuration file was opened for editing:

```bash
sudo nano /etc/redis/redis.conf
```
The following ACL user lines were added at the bottom of the file:

```
# Enable default user but with no dangerous permissions
user default off

# Admin user: full access (only for instructor / DBA)
user admin on >adminStrongPwd ~* +@all

# Application user: can only read/write session keys
user app_user on >appStrongPwd ~session:* +get +set +del +expire +ttl +@connection

# Read-only monitoring user: can read all keys and run INFO
user monitoring on >monitorPwd ~* +@read +info +dbsize +lastsave +@connection

```
![alt text](images/5.png)

**What each line does:**

- `user default off` — disables the built-in default user so unauthenticated connections are blocked.
- `user admin on >adminStrongPwd ~* +@all` — creates an admin user with a password and full access to all keys and commands.
- `user app_user on >appStrongPwd ~session:* +get +set +del +expire +ttl +ping +@connection` — creates an application user that can only read and write keys that start with `session:`. Any other key is off-limits.
- `user monitoring on >monitorPwd ~* +@read +info +dbsize +lastsave +ping +@connection` — creates a read-only user that can view data and run diagnostic commands, but cannot write anything.

Redis was restarted to apply the new configuration:

```bash
sudo systemctl restart redis-server
sudo systemctl status redis-server
```
![alt text](images/6.png)
---

### 4.4 Testing Default User is Blocked

With the default user disabled, an unauthenticated connection was attempted:

```bash
redis-cli ping
```

![alt text](images/7.png)

This shows it's working.

---

### 4.5 Testing the Admin User

The admin user was tested by connecting with its credentials and running several commands:

```bash
redis-cli -u redis://admin:adminStrongPwd@127.0.0.1:6379
```

Inside the session:

```
acl whoami
set mykey "hello"
get mykey
```
![alt text](images/8.png)

The `acl whoami` command confirmed the identity of the connected user. The `set` and `get` commands verified full read/write access.


---

### 4.6 Testing the app_user ACL Restrictions

The application user was connected and tested:

```bash
redis-cli -u redis://app_user:appStrongPwd@127.0.0.1:6379
```

Inside the session:

```
acl whoami
set session:user123 "student_data"
get session:user123
set otherkey "oops"
```

![alt text](images/9.png)

The first `set` command used a key starting with `session:`, which is within the allowed key pattern for this user, so it succeeded. The second `set` command used a key outside the allowed pattern, so it was denied with a `NOPERM` error.

---

### 4.7 Generating TLS Certificates

A dedicated directory was created for the certificate files:
Here, the root-terminal was used so that 'sodo' is not required for each command.

```bash
mkdir -p /etc/redis/tls
cd /etc/redis/tls
```

A Certificate Authority (CA) key and self-signed certificate were created first:

```bash
openssl genrsa -out ca.key 4096

openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 \
  -out ca.crt \
  -subj "/C=BT/ST=Chukha/L=Phuntsholing/O=DBS302/OU=Lab/CN=redis-lab-ca"
```

Then a private key and certificate for the Redis server were generated, signed by the CA:

```bash
openssl genrsa -out redis.key 4096

openssl req -new -key redis.key -out redis.csr \
  -subj "/C=BT/ST=Chukha/L=Phuntsholing/O=DBS302/OU=Lab/CN=localhost"

openssl x509 -req -in redis.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out redis.crt -days 365 -sha256
```

The files were then listed to confirm they were all created:

```bash
ls -la /etc/redis/tls/
```

File permissions were also set so that only the Redis process can read the private key:

```bash
chown redis:redis /etcnt/redis/tls/*
chmod 600 /etc/redis/tls/ca.key
chmod 600 /etc/redis/tls/redis.key
chmod 644 /etc/redis/tls/ca.crt
chmod 644 /etc/redis/tls/redis.crt
```

![alt text](images/10.png)
![alt text](images/11.png)
---

### 4.8 Updating redis.conf for TLS

The configuration file was opened again and the following changes were made:

- The plain TCP port was disabled by changing `port 6379` to `port 0`.
- TLS was enabled by adding the following lines at the bottom of the file (after the ACL user lines):

```
tls-port 6379
tls-ca-cert-file /etc/redis/tls/ca.crt
tls-cert-file /etc/redis/tls/redis.crt
tls-key-file /etc/redis/tls/redis.key
tls-auth-clients yes
```
![alt text](images/12.png)

Redis was restarted:

```bash
sudo systemctl restart redis-server
sudo systemctl status redis-server
```

---

### 4.9 Connecting Over TLS

A TLS connection was made using the `--tls` flag and the CA certificate:

```bash
redis-cli --tls \
  --cacert /etc/redis/tls/ca.crt \
  -u rediss://app_user:appStrongPwd@127.0.0.1:6379
```

Note: `rediss://` (with double `s`) is the scheme that tells `redis-cli` to use TLS.

---
However, when the connection was attempted, the following error appeared:

![alt text](images/13.png)

Upon investigation, the root cause was identified by checking the Redis server version:

The installed version returned v=255.255.255, which is a custom or non-standard build that does not include TLS support. so TLS connections cannot be negotiated regardless of the configuration.

---

## 5. Observations
* Redis ACL authentication worked successfully.
* The admin user had unrestricted database access.
* The restricted user could only access session-related keys.
* Unauthorized key access attempts were blocked.

---
## 7. Conclusion

This part of the practical covered the key steps for securing a Redis server. The default open access was replaced with a proper multi-user ACL system where each user had only the permissions needed for their role. TLS was then layered on top, ensuring that all traffic between the client and server is encrypted and that plain-text connections are no longer possible.

The tests confirmed that both the ACL rules were working correctly, however, the live TLS connection could not be demonstrated because the Redis binary installed on the lab machine was not compiled with TLS support. The NOPERM errors for restricted users showed that the key namespace and command restrictions were being enforced as intended.

---