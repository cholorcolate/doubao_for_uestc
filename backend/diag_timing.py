import time

from rag import RagEngine

eng = RagEngine.instance()

q = "保研名额有多少"

t0 = time.time()
_ = eng.embedder
t1 = time.time()
_ = eng.collection
t2 = time.time()
hits = eng.retrieve(q, None, None)
t3 = time.time()
ans = eng._generate(q, hits)
t4 = time.time()

print(f"embedder 加载: {t1 - t0:.2f}s")
print(f"collection 加载: {t2 - t1:.2f}s")
print(f"retrieve 检索(向量+BM25+rerank): {t3 - t2:.2f}s  命中 {len(hits)} 条")
print(f"generate 生成(LLM): {t4 - t3:.2f}s")
print(f"总耗时: {t4 - t0:.2f}s")
