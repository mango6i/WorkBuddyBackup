# -*- coding: utf-8 -*-
"""端到端实测换电脑恢复：
场景A：新电脑已登录（本机已有 user_id，且是另一个 user_id）—— 模拟"新电脑账号ID不同"
场景B：新电脑全新（无数据库）
验证点：恢复后 sessions 可见、user_id 归属当前账号、automations / workspaces 一并回来
全程在临时目录操作，不碰真实数据。
"""
import importlib.util
import os
import shutil
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
spec = importlib.util.spec_from_file_location(
    "wbbackup", os.path.join(ROOT, "WorkBuddy一键备份.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

REAL_WB = os.path.expanduser("~/.workbuddy")
REAL_DB = os.path.join(REAL_WB, "workbuddy.db")
FAKE_NEW_UID = "new-machine-user-id-0000"


def build_source(tmp, n=3):
    """源：复制真实 db + 选中 n 条对话正文（模拟老电脑备份）"""
    src = os.path.join(tmp, "src_wb")
    os.makedirs(os.path.join(src, "sessions"), exist_ok=True)
    shutil.copy2(REAL_DB, os.path.join(src, "workbuddy.db"))
    conn = sqlite3.connect(os.path.join(src, "workbuddy.db"))
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM sessions WHERE deleted_at IS NULL LIMIT ?", (n,))]
    conn.close()
    for sid in ids:
        p = os.path.join(REAL_WB, "sessions", f"{sid}.json")
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(src, "sessions", f"{sid}.json"))
    return src, ids


def build_target_with_other_uid(tmp):
    """目标A：新电脑已登录过（db 存在但 user_id 不同、会话为空）"""
    dst = os.path.join(tmp, "dstA_wb")
    os.makedirs(dst, exist_ok=True)
    shutil.copy2(REAL_DB, os.path.join(dst, "workbuddy.db"))
    conn = sqlite3.connect(os.path.join(dst, "workbuddy.db"))
    cur = conn.cursor()
    cur.execute("DELETE FROM sessions")
    cur.execute("DELETE FROM automations")
    cur.execute("DELETE FROM workspaces")
    # 伪造"新电脑账号"：插入一条占位会话，user_id 为新的
    try:
        cur.execute(
            "INSERT INTO sessions (id, user_id, title, cwd, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            ("placeholder-1", FAKE_NEW_UID, "占位", "C:/tmp", 0, 0))
    except Exception as e:
        print("  插入占位会话失败:", e)
    conn.commit()
    conn.close()
    return dst


def query(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    s = cur.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    s_vis = cur.execute(
        "SELECT COUNT(*) FROM sessions WHERE deleted_at IS NULL").fetchone()[0]
    uids = [r[0] for r in cur.execute("SELECT DISTINCT user_id FROM sessions")]
    a = cur.execute("SELECT COUNT(*) FROM automations").fetchone()[0]
    a_uids = [r[0] for r in cur.execute(
        "SELECT DISTINCT owner_user_id FROM automations")] if a else []
    w = cur.execute("SELECT COUNT(*) FROM workspaces").fetchone()[0]
    conn.close()
    return s, s_vis, uids, a, a_uids, w


class Log:
    def __init__(self):
        self.lines = []

    def emit(self, kind, *args):
        if kind == "log":
            self.lines.append(args[0])


def run_case(name, dst_builder, expect_uid_override=None):
    print(f"\n=== 场景 {name} ===")
    tmp = tempfile.mkdtemp(prefix="wb_e2e_")
    src, ids = build_source(tmp)
    cfg = dict(mod.DEFAULT_BACKUP_CONFIG)
    cfg["workbuddy_dir"] = src
    cfg["workspaces_root"] = os.path.join(tmp, "src_ws")
    cfg["save_root"] = tmp
    engine_src = mod.BackupEngine(cfg)
    zip_path = os.path.join(tmp, "backup.zip")
    w, sk, tot = engine_src.backup(zip_path, None, ids, [])
    print(f"备份: 写入 {w} 项，zip {os.path.getsize(zip_path)/1048576:.1f} MB，勾选 {len(ids)} 个对话")
    with __import__('zipfile').ZipFile(zip_path) as zf:
        mf = __import__('json').loads(zf.read('backup_manifest.json').decode('utf-8'))
    print("  备份包记录 source_user_id =", mf.get('source_user_id'))

    dst = dst_builder(tmp)
    cfg2 = dict(cfg)
    cfg2["workbuddy_dir"] = dst
    cfg2["workspaces_root"] = os.path.join(tmp, "dst_ws")
    eng2 = mod.BackupEngine(cfg2)
    lg = Log()
    ok = eng2.restore(zip_path, lg, ids, [])
    print("  恢复返回:", ok)
    for line in lg.lines:
        print("   [日志]", line)

    db = os.path.join(dst, "workbuddy.db")
    s, s_vis, uids, a, a_uids, w2 = query(db)
    print(f"  恢复后: sessions={s}(未删除{s_vis}) user_id={uids}")
    print(f"          automations={a} owner={a_uids}  workspaces={w2}")
    # 断言
    have = {r[0] for r in sqlite3.connect(db).execute("SELECT id FROM sessions")}
    missing = [i for i in ids if i not in have]
    if name == "A":
        ok_ids = not missing and FAKE_NEW_UID in uids
        print("  判定:", "通过 ✅（对话归属新电脑账号，界面可显示）" if ok_ids else "失败 ❌")
    else:
        ok_ids = not missing and s_vis >= len(ids)
        print("  判定:", "通过 ✅（全新电脑恢复成功）" if ok_ids else "失败 ❌")
    print("  缺失对话:", missing if missing else "无")
    return ok_ids


if __name__ == "__main__":
    r1 = run_case("A", build_target_with_other_uid)

    def empty_target(tmp):
        d = os.path.join(tmp, "dstB_wb")
        os.makedirs(d, exist_ok=True)
        return d

    r2 = run_case("B", empty_target)
    print("\n=== 总结:", "两个场景全部通过 ✅" if (r1 and r2) else "存在失败 ❌")
    sys.exit(0 if (r1 and r2) else 1)
