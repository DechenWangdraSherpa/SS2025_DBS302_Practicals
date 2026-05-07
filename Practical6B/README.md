# DBS302 
## Practical 6 - Part B Report
### Securing MongoDB

---

## 1. Introduction

This report covers the steps taken to secure a MongoDB instance as part of the DBS302 lab practical. By default, MongoDB does not implement access control, which means any client that can reach the port can read and write data freely. This is a serious security concern in any real environment.

The lab focused on three main areas:

- **Authentication** – requiring users to log in before accessing anything
- **Role-Based Access Control (RBAC)** – giving users only the permissions they actually need
- **TLS Encryption** – encrypting all traffic between the client and the MongoDB server

---

## 2. Step 0 – Starting MongoDB Without Auth (Initial Setup Only)

Before setting up any security, MongoDB was started without authentication to create the first admin user. Once the admin user exists, authentication can be turned on.

The lab guide suggested starting MongoDB manually with:

```bash
mongod --dbpath /data/db --bind_ip 127.0.0.1 --port 27017
```

However, this command failed on my Kali system because MongoDB was already running as a system service on port 27017. Instead, the existing service was started through `systemctl`:

```bash
sudo systemctl start mongodb
```

Then, `mongosh` was used to connect:

```bash
mongosh
```

At this point, no credentials were needed — anyone on the machine could connect and do anything.

![alt text](Images/1.1.png)
![alt text](Images/1.2.png)

---

## 3. Step 1 – Creating the First Admin User

Inside the `mongosh` the following command was used to create the admin database and assign user roles:

```js
use admin;

db.createUser({
  user: "rootAdmin",
  pwd: "rootStrongPwd",
  roles: [
    { role: "userAdminAnyDatabase", db: "admin" },
    { role: "dbAdminAnyDatabase", db: "admin" },
    { role: "readWriteAnyDatabase", db: "admin" }
  ]
});
```

![alt text](Images/2.1.png)

---

## 4. Step 2 – Enable Authentication in mongod.conf

Once the admin user was in place, authentication was enabled by editing the MongoDB configuration file.

The lab guide specified editing `/etc/mongod.conf` using YAML syntax:
 
```yaml
security:
  authorization: "enabled"
```

However, on my system, the MongoDB installation used the older `mongodb.service` rather than `mongod.service`, and its configuration file was `/etc/mongodb.conf` in the older INI format — not YAML. The YAML-style `security:` block is not recognised by this version, so the setting had no effect when tried.

The correct way to enable authentication in the INI-style config file is:

```ini
auth = true
```

This single line was added to `/etc/mongodb.conf`.

![alt text](Images/3.2.png)

MongoDB was then restarted to apply the change:

```bash
sudo systemctl restart mongodb
```

![alt text](Images/4.1.png)

From this point on, every connection attempt requires valid credentials.

---

## 5. Step 3 – Test Authentication

### 5.1 Authenticated Connection

An authenticated connection was made using the `rootAdmin` credentials:

```bash
mongosh --host 127.0.0.1 --port 27017 \
  -u rootAdmin -p rootStrongPwd \
  --authenticationDatabase admin
```

The `connectionStatus` command was run to verify the session:

```js
db.runCommand({ connectionStatus: 1 });
```

The output showed `rootAdmin` as the authenticated user.

![alt text](Images/4.2.png)

### 5.2 Unauthenticated Connection (Expected Failure)

To confirm that the server now rejects unauthenticated clients, a connection was attempted without any credentials:

```bash
mongosh --host 127.0.0.1 --port 27017
```

Running `show dbs` inside this session returned an authorization error.

![alt text](Images/5.png)

This confirms that setting `auth = true` in `/etc/mongodb.conf` works — unauthenticated clients cannot access any data.

---

## 6. Step 4 – Create Application Database, Role, and User (RBAC)

### 6.1 Creating the Application Role and User

After authenticating as `rootAdmin`, a dedicated application database (`myapp`) was set up, using the following command:

```js
use myapp;

db.runCommand({
  createRole: "myAppRole",
  privileges: [
    {
      resource: { db: "myapp", collection: "customers" },
      actions: ["find", "insert", "update", "remove"]
    }
  ],
  roles: []
});

db.createUser({
  user: "appUser",
  pwd: "appStrongPwd",
  roles: [
    { role: "myAppRole", db: "myapp" }
  ]
});
```

Here the `appUser` has least privilege so, it can only do what the application actually needs, nothing more.

![alt text](Images/6.png)

### 6.2 Testing RBAC as appUser

Logging in as `appUser`:

```bash
mongosh --host 127.0.0.1 --port 27017 \
  -u appUser -p appStrongPwd \
  --authenticationDatabase myapp
```

The allowed operations on `myapp.customers` worked without issue:

```js
use myapp;
db.customers.insertOne({ name: "Student One", city: "Phuntsholing" });
db.customers.find();
```

![alt text](Images/7.1.png)

However, attempting to access the `admin` database was denied:

```js
use admin;
db.system.users.find();
```
![alt text](Images/7.2.png)

This returned an authorization error, as expected. The `appUser` account has no permissions outside of `myapp.customers`.

This demonstrates that RBAC is working.

---

## 7. Step 5 – Enable TLS Encryption for MongoDB

### 7.1 Generating Self-Signed Certificates

To encrypt traffic between clients and the server, TLS was configured using self-signed certificates.

```bash
mkdir -p /etc/mongo/tls
cd /etc/mongo/tls
```

A Certificate Authority (CA) was generated first, then a server certificate was signed by that CA, and finally both the key and certificate were combined into a single PEM file that MongoDB uses:

```bash
# CA key and certificate
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 365 \
  -out ca.pem \
  -subj "/C=BT/ST=Chukha/L=Phuntsholing/O=DBS302/OU=Lab/CN=mongo-lab-ca"

# Server key and certificate
openssl genrsa -out mongo.key 4096
openssl req -new -key mongo.key -out mongo.csr \
  -subj "/C=BT/ST=Chukha/L=Phuntsholing/O=DBS302/OU=Lab/CN=localhost"
openssl x509 -req -in mongo.csr -CA ca.pem -CAkey ca.key -CAcreateserial \
  -out mongo.crt -days 365 -sha256

# Combine into single PEM for MongoDB
cat mongo.key mongo.crt > mongo.pem
```

![alt text](Images/8.1.png)
![alt text](Images/8.2.png)

### 7.2 Updating the Config file for TLS

The lab guide specified adding TLS settings using YAML syntax in `/etc/mongod.conf`:

```yaml
net:
  port: 27017
  bindIp: 0.0.0.0
  tls:
    mode: requireTLS
    certificateKeyFile: /etc/mongo/tls/mongo.pem
    CAFile: /etc/mongo/tls/ca.pem
    allowConnectionsWithoutCertificates: true

security:
  authorization: "enabled"
```

However, because my system uses the older `mongodb.service` with the INI-style `/etc/mongodb.conf`, the `net:` and `security:`. The equivalent settings in INI format were added to `/etc/mongodb.conf`:

```ini
bind_ip = 127.0.0.1
auth = true
 
sslOnNormalPorts = true
sslPEMKeyFile = /etc/mongo/tls/mongo.pem
sslCAFile = /etc/mongo/tls/ca.pem
sslWeakCertificateValidation = true
```

![alt text](Images/9.png)

MongoDB was restarted:

```bash
sudo systemctl restart mongod
```

### 7.3 Connect with TLS and Auth

A connection was established as `appUser` with TLS enabled:

```bash
mongosh \
  --host 127.0.0.1 \
  --port 27017 \
  --tls \
  --tlsCAFile /etc/mongo/tls/ca.pem \
  --tlsAllowInvalidHostnames \
  -u appUser -p appStrongPwd \
  --authenticationDatabase myapp
```

Inside mongosh, a few operations were run to confirm everything works:

```js
use myapp;
db.customers.insertOne({ name: "TLS Test", city: "Thimphu" });
db.customers.find();
```

![alt text](Images/10.png)


### 7.4 Verifying TLS is Enforced

A connection was attempted without the `--tls` flag to confirm that unencrypted connections are rejected:

```bash
mongosh --host 127.0.0.1 --port 27017 \
  -u appUser -p appStrongPwd \
  --authenticationDatabase myapp
```

This failed with a connection error, confirming that `requireTLS` mode is enforced and MongoDB will not accept plain connections.

![alt text](Images/11.png)

---

## 8. (Optional) Simple Application Code Demo for MongoDB (Node.js)

A simple Node.js script was written to demonstrate how an application connects to a secured MongoDB instance using both TLS and authentication programmatically.

```js
const { MongoClient } = require("mongodb");

async function main() {
  const uri = "mongodb://appUser:appStrongPwd@127.0.0.1:27017/myapp?tls=true";

  const client = new MongoClient(uri, {
    tlsCAFile: "/etc/mongo/tls/ca.pem",
  });

  try {
    await client.connect();
    console.log("Connected to MongoDB with TLS and auth");

    const db = client.db("myapp");
    const customers = db.collection("customers");

    await customers.insertOne({ name: "Node Client", city: "Phuntsholing" });
    const docs = await customers.find({}).toArray();
    console.log("Customers:", docs);
  } finally {
    await client.close();
  }
}

main().catch(console.error);
```

Running the script with `node mongo_secure_demo.js` printed the connected message and the list of documents from the `customers` collection.

![alt text](Images/12.png)

---

---

## Conclusion

By the end of this practical, the MongoDB which was completely open went from having no access control at all to requiring a username, password, and an encrypted connection to use the database. Authentication handles who can connect, RBAC controls the roles of the users once they are in, and TLS makes sure the data cannot be read in transit.

---