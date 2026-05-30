import time
import uuid
import redis
import pymongo
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

# -------------------------------------------------------------------
# Connection setup
# -------------------------------------------------------------------

# Redis connection
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# MongoDB connection
mongo_client = pymongo.MongoClient(
    "mongodb://admin:password123@localhost:27017/"
)
mongo_db = mongo_client["benchmark_db"]
mongo_posts = mongo_db["posts"]
mongo_posts.drop()  # Clean up before benchmark

# Cassandra connection
cass_cluster = Cluster(['localhost'])
cass_session = cass_cluster.connect()

cass_session.execute("""
    CREATE KEYSPACE IF NOT EXISTS benchmark
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
""")
cass_session.set_keyspace('benchmark')
cass_session.execute("DROP TABLE IF EXISTS posts_bench")
cass_session.execute("""
    CREATE TABLE posts_bench (
        user_id  UUID,
        post_id  UUID,
        content  TEXT,
        created_at TIMESTAMP,
        PRIMARY KEY (user_id, created_at, post_id)
    ) WITH CLUSTERING ORDER BY (created_at DESC, post_id ASC)
""")

# -------------------------------------------------------------------
# Benchmark parameters
# -------------------------------------------------------------------
NUM_WRITES = 500
user_id = "user_bench_001"
cass_user_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

# -------------------------------------------------------------------
# Write benchmark
# -------------------------------------------------------------------
print(f"\n--- Write Benchmark ({NUM_WRITES} records) ---")

# Redis writes
start = time.time()
pipe = r.pipeline()
for i in range(NUM_WRITES):
    post_id = f"bench_post_{i}"
    pipe.hset(f"post:{post_id}", mapping={
        "user_id": user_id,
        "content": f"Benchmark post number {i} for Redis performance testing.",
        "timestamp": "2025-05-01T10:00:00Z"
    })
    pipe.lpush(f"timeline:{user_id}", post_id)
pipe.execute()
redis_write_time = time.time() - start
print(f"  Redis   : {redis_write_time:.4f}s  ({NUM_WRITES/redis_write_time:.0f} ops/sec)")

# MongoDB writes
start = time.time()
docs = [
    {
        "_id": f"bench_post_{i}",
        "user_id": user_id,
        "content": f"Benchmark post number {i} for MongoDB performance testing.",
        "created_at": "2025-05-01T10:00:00Z"
    }
    for i in range(NUM_WRITES)
]
mongo_posts.insert_many(docs)
mongo_write_time = time.time() - start
print(f"  MongoDB : {mongo_write_time:.4f}s  ({NUM_WRITES/mongo_write_time:.0f} ops/sec)")

# Cassandra writes
prepared = cass_session.prepare("""
    INSERT INTO posts_bench (user_id, post_id, content, created_at)
    VALUES (?, ?, ?, toTimestamp(now()))
""")
start = time.time()
for i in range(NUM_WRITES):
    cass_session.execute(prepared, (cass_user_id, uuid.uuid4(),
                                    f"Benchmark post number {i} for Cassandra performance testing."))
cass_write_time = time.time() - start
print(f"  Cassandra: {cass_write_time:.4f}s  ({NUM_WRITES/cass_write_time:.0f} ops/sec)")

# -------------------------------------------------------------------
# Read benchmark
# -------------------------------------------------------------------
print(f"\n--- Read Benchmark (retrieve {NUM_WRITES} records) ---")

# Redis reads
start = time.time()
post_ids = r.lrange(f"timeline:{user_id}", 0, NUM_WRITES - 1)
pipe = r.pipeline()
for pid in post_ids:
    pipe.hgetall(f"post:{pid}")
pipe.execute()
redis_read_time = time.time() - start
print(f"  Redis   : {redis_read_time:.4f}s  ({NUM_WRITES/redis_read_time:.0f} ops/sec)")

# MongoDB reads
mongo_posts.create_index([("user_id", pymongo.ASCENDING)])
start = time.time()
results = list(mongo_posts.find({"user_id": user_id}))
mongo_read_time = time.time() - start
print(f"  MongoDB : {mongo_read_time:.4f}s  ({len(results)/mongo_read_time:.0f} ops/sec)")

# Cassandra reads
start = time.time()
rows = list(cass_session.execute(
    "SELECT * FROM posts_bench WHERE user_id = %s LIMIT %s",
    (cass_user_id, NUM_WRITES)
))
cass_read_time = time.time() - start
print(f"  Cassandra: {cass_read_time:.4f}s  ({len(rows)/cass_read_time:.0f} ops/sec)")

print("\n--- Benchmark Complete ---\n")

# Cleanup
mongo_client.close()
cass_cluster.shutdown()
