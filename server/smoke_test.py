"""M0 冒烟测试：用 FastAPI TestClient 一次性打完全部接口。

设计要点（避免长驻进程拖慢会话）：
- 不启动 uvicorn，不占用端口，不留孤儿进程
- 用 ``TestClient(app).__enter__()`` 显式触发 startup（seed 示例数据）
- 毫秒级返回，可直接 ``python server/smoke_test.py`` 运行

用法：
    python server/smoke_test.py          # 从项目根运行
    python -m server.smoke_test          # 亦可
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

ok = True
_failed: list[str] = []


def check(name: str, cond: bool, extra="") -> None:
    global ok
    mark = "  PASS  " if cond else "  FAIL  "
    print(mark + name + (f"   {extra}" if extra != "" else ""))
    if not cond:
        ok = False
        _failed.append(name)


def _restore_user_data(c, pid: str, backup: dict) -> None:
    """把示例项目还原成冒烟开跑前的样子。

    **教训（2026-09-27）**：早期版本的用例直接往示例项目写 brief、再写 `{}` 清空，
    把用户填好的「项目设定」每次跑冒烟都冲掉一次；批量更新用例还会把示例卡牌的
    数值改成 5 且不还原。所以现在开跑先整份备份，`finally` 里无条件还原。
    """
    try:
        # force=true：还原时如果服务器上还是冒烟写的非空假数据，不加 force 会被防空闸拦下
        c.put(f"/api/projects/{pid}/brief?force=true", json=backup["brief"])
        keep_tpl = {t["id"] for t in backup["templates"]}
        for t in backup["templates"]:
            c.put(f"/api/templates/{t['id']}", json={
                "projectId": pid, "name": t["name"], "fields": t["fields"],
                "background": t["background"]})
        keep_card = {x["id"] for x in backup["cards"]}
        for x in c.get(f"/api/projects/{pid}/cards").json():
            if x["id"] not in keep_card:                    # 冒烟新建的卡
                c.delete(f"/api/cards/{x['id']}?pid={pid}")
        for x in backup["cards"]:                           # 恢复卡牌字段与标签
            c.put(f"/api/cards/{x['id']}", json={**x, "projectId": pid})
        for t in c.get(f"/api/projects/{pid}/templates").json():
            if t["id"] not in keep_tpl:                     # 冒烟新建的模板
                c.delete(f"/api/templates/{t['id']}?pid={pid}")
        print("  [cleanup] 已还原示例项目（brief / 模板 / 卡牌）")
    except Exception as e:                                  # noqa: BLE001
        print(f"  [warn] 还原示例项目失败：{e}")


def main() -> int:
    t0 = time.perf_counter()
    c = TestClient(app)
    c.__enter__()  # 触发 startup：seed 示例项目/模板/卡牌 + 内置 icon 库
    backup = None
    pid = ""
    try:
        print("[health]")
        r = c.get("/api/health")
        check("health", r.status_code == 200, r.json())

        print("[projects]")
        r = c.get("/api/projects")
        check("list", r.status_code == 200)
        projects = r.json()
        # 清理上一轮异常中断残留的临时项目（保证可重复运行）
        for stale in [p for p in projects if p["name"] == "冒烟测试项目"]:
            c.delete(f"/api/projects/{stale['id']}")
            projects.remove(stale)
        check("seed 了一个示例项目", len(projects) >= 1, [p["name"] for p in projects])
        if not projects:
            return 1
        # 固定挑「有模板」的项目，避免依赖排序
        pid = next((p["id"] for p in projects if p.get("templateCount")), projects[0]["id"])
        if not c.get(f"/api/projects/{pid}/templates").json():
            pid = next((p["id"] for p in projects
                        if c.get(f"/api/projects/{p['id']}/templates").json()), pid)

        r = c.post("/api/projects", json={"name": "冒烟测试项目", "tags": ["tmp"]})
        check("create", r.status_code == 200)
        new_pid = r.json()["id"] if r.status_code == 200 else None

        # ---- 先备份用户数据：下面这些用例会写 brief / 模板字段 / 卡牌 ----
        proj0 = c.get(f"/api/projects/{pid}").json()
        backup = {
            "brief": proj0.get("brief") or {},
            "templates": [{"id": t["id"], "name": t.get("name"), "fields": t.get("fields")}
                          for t in c.get(f"/api/projects/{pid}/templates").json()],
            "cards": [c.get(f"/api/cards/{x['id']}?pid={pid}").json()
                      for x in c.get(f"/api/projects/{pid}/cards").json()],
        }
        for t in backup["templates"]:
            t["background"] = (c.get(f"/api/templates/{t['id']}?pid={pid}").json()
                               .get("background") or {})
        check("已备份示例项目（brief/模板/卡牌）", backup["brief"] is not None)

        # 项目设定 ProjectBrief（§4.4）：UI 表单 + AI 语料层的共同数据源
        print("[项目设定 ProjectBrief]")
        r = c.put(f"/api/projects/{pid}/brief", json={
            "title": "星域争霸", "oneLiner": "争夺星区资源的快节奏对抗卡牌",
            "synopsis": "旧帝国崩溃后，各派系争夺星区。",
            "genre": ["卡牌对战", "资源管理"], "keywords": ["星际", "舰队"],
            "players": "2-4 人",
            "artStyle": {"style": "厚涂数字绘画", "palette": ["#0b1a2b", "#c9a227"],
                         "mood": ["史诗", "冷峻"], "details": "笔触粗犷"},
            "factions": [{"name": "铁壁议会", "desc": "重工业冷灰蓝", "color": "#5a6b7c"}],
            "taboos": ["不要文字"],
        })
        check("保存项目设定", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
        b = r.json().get("brief", {}) if r.status_code == 200 else {}
        check("brief 字段落盘", b.get("oneLiner") == "争夺星区资源的快节奏对抗卡牌"
              and b.get("artStyle", {}).get("style") == "厚涂数字绘画"
              and b.get("artStyle", {}).get("palette") == ["#0b1a2b", "#c9a227"],
              {k: b.get(k) for k in ("title", "players")})
        check("brief 写入 updatedAt", bool(b.get("updatedAt")))
        check("派系落盘", len(b.get("factions", [])) == 1 and b["factions"][0]["color"] == "#5a6b7c")
        r2 = c.put(f"/api/projects/{pid}/brief",
                   json={"keywords": ["星际", "星际", "  ", "舰队"], "genre": ["卡牌对战", "卡牌对战"]})
        b2 = r2.json()["brief"]
        check("关键词去重去空白", b2["keywords"] == ["星际", "舰队"], b2["keywords"])
        check("类型去重", b2["genre"] == ["卡牌对战"], b2["genre"])
        check("GET 项目带回 brief", "brief" in c.get(f"/api/projects/{pid}").json())
        check("列表接口带回 brief",
              any("brief" in p for p in c.get("/api/projects").json()))
        r3 = c.put("/api/projects/p_not_exist/brief", json={"title": "x"})
        check("不存在的项目返回 404", r3.status_code == 404, r3.status_code)
        # 还原示例项目（脏数据会干扰人工查看）
        # 防误清空：非空设定只用一个空 body 冲不掉（真出过"脚本把用户设定冲空"的事故）
        r = c.put(f"/api/projects/{pid}/brief", json={})
        check("防误清空：非空时清空被拦（409）", r.status_code == 409, r.status_code)
        r = c.put(f"/api/projects/{pid}/brief?force=true", json={})
        check("带 force 可清空", r.status_code == 200
              and not r.json()["brief"].get("oneLiner"))

        print("[templates]")
        r = c.get(f"/api/projects/{pid}/templates")
        check("list templates", r.status_code == 200 and len(r.json()) >= 1)
        # 固定用「字段最多」的模板跑后续用例（示例项目里就是「法术卡」）。
        # 不能假定 tpls[0] —— 列表按修改时间排序，用户自己新建的模板会插到前面，
        # 断言就会莫名失败。
        tpls = sorted(r.json(), key=lambda t: (-len(t.get("fields") or []),
                                              t.get("name") != "法术卡"))
        tid = tpls[0]["id"]
        check("模板有字段", len(tpls[0]["fields"]) >= 5, len(tpls[0]["fields"]))

        r = c.put(f"/api/templates/{tid}", json={"projectId": pid, "name": "法术卡(改)"})
        check("update template", r.status_code == 200 and r.json()["name"] == "法术卡(改)")
        c.put(f"/api/templates/{tid}", json={"projectId": pid, "name": tpls[0]["name"]})

        # guide（隐形定位框，G1）：AI 底板流程靠它标记区域，必须能落盘并读回
        f0 = tpls[0]["fields"][0]
        c.put(f"/api/templates/{tid}", json={
            "projectId": pid,
            "fields": [{**f0, "guide": True}] + tpls[0]["fields"][1:]})
        back = c.get(f"/api/templates/{tid}?pid={pid}").json()
        g = next((f for f in back["fields"] if f["id"] == f0["id"]), {})
        check("guide 定位框可存取", g.get("guide") is True, g.get("guide"))
        check("其余字段 guide 默认 False",
              all(not f.get("guide") for f in back["fields"] if f["id"] != f0["id"]))
        c.put(f"/api/templates/{tid}", json={"projectId": pid, "fields": tpls[0]["fields"]})

        # 底板挖空（background.mask，净尺寸设计坐标；渲染器用 evenodd clipPath 抠掉）。
        # background 是自由 dict，这里确认能原样存取。
        bg0 = dict(tpls[0].get("background") or {})
        c.put(f"/api/templates/{tid}", json={"projectId": pid,
              "background": {**bg0, "mask": [[10, 20, 100, 60], [200, 300, 50, 50]]}})
        back = c.get(f"/api/templates/{tid}?pid={pid}").json()
        check("底板挖空区域可存取",
              back["background"].get("mask") == [[10, 20, 100, 60], [200, 300, 50, 50]],
              back["background"].get("mask"))
        c.put(f"/api/templates/{tid}", json={"projectId": pid, "background": bg0})
        check("清空后 mask 消失",
              not (c.get(f"/api/templates/{tid}?pid={pid}").json()
                   ["background"].get("mask")))

        # 换一张底板图时，旧图上的挖空区要自动丢弃（在临时模板上验证，不碰用户模板）
        bps = c.get("/api/assets?type=baseplate").json()
        if len(bps) >= 2:
            rt = c.post(f"/api/projects/{pid}/templates", json={"name": "挖空临时模板"})
            rtid = rt.json()["id"]
            c.put(f"/api/templates/{rtid}", json={"projectId": pid, "background": {
                "assetId": bps[0]["id"], "bleedPx": 36, "mask": [[5, 5, 20, 20]]}})
            ar = c.post(f"/api/projects/{pid}/ai/baseplate/apply"
                        f"?templateId={rtid}&assetId={bps[1]['id']}")
            check("换底板后旧挖空区被丢弃",
                  ar.status_code == 200 and not ar.json()["background"].get("mask"),
                  ar.json().get("background") if ar.status_code == 200 else ar.text[:120])
            check("同图重应用保留挖空区",
                  (c.put(f"/api/templates/{rtid}", json={"projectId": pid, "background": {
                      "assetId": bps[1]["id"], "bleedPx": 36, "mask": [[7, 7, 30, 30]]}})
                   .status_code == 200)
                  and (c.post(f"/api/projects/{pid}/ai/baseplate/apply"
                              f"?templateId={rtid}&assetId={bps[1]['id']}")
                       .json()["background"].get("mask") == [[7, 7, 30, 30]]))
            c.delete(f"/api/templates/{rtid}?pid={pid}")

        # 新建模板时可选常见卡牌尺寸（物理 mm 优先，像素按 DPI 换算）
        r = c.post(f"/api/projects/{pid}/templates", json={
            "name": "尺寸测试模板",
            "canvas": {"w": 520, "h": 791, "dpi": 300, "bleed": 35, "w_mm": 44, "h_mm": 67}})
        check("新建模板可指定尺寸",
              r.status_code == 200 and r.json()["canvas"]["w"] == 520
              and r.json()["canvas"]["h"] == 791 and r.json()["canvas"]["w_mm"] == 44,
              r.json().get("canvas") if r.status_code == 200 else r.text[:120])
        if r.status_code == 200:
            c.delete(f"/api/templates/{r.json()['id']}?pid={pid}")
        r = c.post(f"/api/projects/{pid}/templates",
                   json={"name": "越界尺寸", "canvas": {"w": 99999, "h": 10, "dpi": 9999}})
        check("离谱尺寸被夹取",
              r.status_code == 200 and r.json()["canvas"]["w"] == 8192
              and r.json()["canvas"]["h"] == 64 and r.json()["canvas"]["dpi"] == 1200,
              r.json().get("canvas") if r.status_code == 200 else r.text[:120])
        if r.status_code == 200:
            c.delete(f"/api/templates/{r.json()['id']}?pid={pid}")

        # AI 语料层（§6.11）：提示词预览只读接口。下面几条是 Spike 实测出的硬规则，
        # 一旦回归（比如又用百分比描述、漏掉某个区域、忘了禁画框）这里就会红。
        print("[AI 语料层：提示词预览]")
        r = c.get("/api/ai/health")
        check("AI 健康接口", r.status_code == 200 and "providers" in r.json())
        models = c.get("/api/ai/models").json()
        check("能力表记录 auto 不支持",
              models["qwen-image-3.0-pro"]["supports"]["auto"] is False)
        r = c.post(f"/api/projects/{pid}/preview-prompt", json={"templateId": tid})
        pv = r.json()
        check("提示词预览可用", r.status_code == 200 and len(pv["prompt"]) > 100,
              r.text[:120] if r.status_code != 200 else len(pv["prompt"]))
        check("硬规则·逐区点名（含右上角小方块）",
              "右上角的独立小方块" in pv["prompt"] and "大矩形区域" in pv["prompt"])
        check("硬规则·禁止画框", "不要画框" in pv["prompt"])
        check("硬规则·图片位留空（不画插画）",
              "配图空位" in pv["prompt"] and "不要画任何插画" in pv["prompt"])
        check("硬规则·材质连续、禁止白块",
              "不要出现白色、灰白色的空白面板" in pv["prompt"]
              and "白色面板" in pv["negative_prompt"])
        check("负向词含文字/边框",
              "文字" in pv["negative_prompt"] and "边框" in pv["negative_prompt"])
        check("分区数 = 字段数", len(pv["zones"]) == len(tpls[0]["fields"]),
              f'{len(pv["zones"])} vs {len(tpls[0]["fields"])}')
        c.put(f"/api/projects/{pid}/brief", json={
            "artStyle": {"style": "厚涂数字绘画", "palette": ["#0b1a2b"], "mood": ["史诗"]},
            "keywords": ["星际"], "taboos": ["不要文字"]})
        pv2 = c.post(f"/api/projects/{pid}/preview-prompt", json={"templateId": tid}).json()
        check("语料块注入风格/配色/关键词/禁忌",
              "[风格] 厚涂数字绘画" in pv2["prompt"] and "#0b1a2b" in pv2["prompt"]
              and "星际" in pv2["prompt"], pv2["blocks"])
        txt = c.post(f"/api/projects/{pid}/preview-prompt",
                     json={"templateId": tid, "kind": "text"}).json()
        check("文生文 system 含字段定义",
              "字段定义" in txt["prompt"] and '"cost"' in txt["prompt"])
        # 临时补充提示词（用户可写入一句，只影响这一次生成）
        pvx = c.post(f"/api/projects/{pid}/preview-prompt",
                     json={"templateId": tid, "extra": "整体偏暖的金色调"}).json()
        check("临时提示词进入 prompt", "整体偏暖的金色调" in pvx["prompt"])
        cv0 = tpls[0]["canvas"]
        expect_bp = f'{cv0["w"] + cv0["bleed"] * 2}x{cv0["h"] + cv0["bleed"] * 2}'
        check("底板尺寸含出血", pvx["size"] == expect_bp,
              f'{pvx["size"]} vs {expect_bp}（净 {cv0["w"]}×{cv0["h"]} + 出血 {cv0["bleed"]}）')
        check("提示词含出血约束", "出血区" in pvx["prompt"] and "会被裁掉" in pvx["prompt"])
        # 卡图：尺寸取该图片区域大小（过小时等比放大到安全下限）
        art = next(f for f in tpls[0]["fields"] if f["kind"] == "image")
        seeded = c.get(f"/api/projects/{pid}/cards").json()
        card_id_for_art = seeded[0]["id"] if seeded else ""
        pvc = c.post(f"/api/projects/{pid}/preview-prompt",
                     json={"kind": "cardart", "templateId": tid, "cardId": card_id_for_art,
                           "fieldKey": art["key"], "extra": "电影感"}).json()
        wq, hq = (int(v) for v in pvc["size"].split("x"))
        check("卡图尺寸按区域等比",
              min(wq, hq) >= 512 and abs(wq / hq - art["rect"][2] / art["rect"][3]) < 0.05,
              f'{pvc["size"]} vs rect {art["rect"][2]}x{art["rect"][3]}')
        check("卡图 prompt 带上卡面文字", "画面依据" in pvc["prompt"])
        # job 接口与校验（不真跑生成，避免花钱）
        check("job 列表可用", isinstance(c.get(f"/api/ai/jobs?pid={pid}").json(), list))
        check("取消不存在的 job 返回 404",
              c.post("/api/ai/jobs/job_nope/cancel").status_code == 404)
        check("应用不存在的资源返回 404",
              c.post(f"/api/projects/{pid}/ai/baseplate/apply"
                     f"?templateId={tid}&assetId=as_nope").status_code == 404)
        check("卡图缺少 cardId 返回 400",
              c.post(f"/api/projects/{pid}/ai/cardart", json={"templateId": tid}).status_code == 400)

        c.put(f"/api/projects/{pid}/brief?force=true", json={})
        r = c.post(f"/api/projects/{pid}/preview-prompt", json={"templateId": "tpl_nope"})
        check("模板不存在返回 400", r.status_code == 400, r.status_code)

        print("[cards]")
        # 先清掉上一轮异常中断（比如被手动取消）可能残留的测试卡，保证可重复运行
        for x in c.get(f"/api/projects/{pid}/cards").json():
            if x["name"].startswith(("测试卡", "映射卡", "批量删")):
                c.delete(f"/api/cards/{x['id']}?pid={pid}")
        r = c.get(f"/api/projects/{pid}/cards")
        base_cards = r.json() if r.status_code == 200 else []
        # 不能写死 3：示例项目是用户的地盘，他自己加的卡（如"新卡牌"）也算数
        check("list cards（至少 3 张种子卡）",
              r.status_code == 200 and len(base_cards) >= 3, len(base_cards))

        r = c.post(f"/api/projects/{pid}/cards/import", json={
            "templateId": tid, "format": "csv",
            "payload": "name,cost,desc\n测试卡A,2,描述A\n测试卡B,9,描述B\n",
            "mode": "append"})
        check("csv 导入", r.status_code == 200 and r.json()["created"] == 2,
              r.json().get("created") if r.status_code == 200 else r.text)
        cards = c.get(f"/api/projects/{pid}/cards").json()
        check("导入后总数 +2", len(cards) == len(base_cards) + 2, len(cards))
        print("   卡牌:", sorted(x["name"] for x in cards))

        # 清理导入的两张卡，保持示例数据干净
        for x in cards:
            if x["name"].startswith("测试卡"):
                c.delete(f"/api/cards/{x['id']}?pid={pid}")
        cards = c.get(f"/api/projects/{pid}/cards").json()

        print("[M2 批量更新 / 数据导出]")
        # 表格批量模式：一次改多张卡的字段
        rows = [{
            "id": x["id"], "name": x["name"], "tags": ["批量"],
            "fields": {"cost": 5}
        } for x in cards]
        r = c.post(f"/api/projects/{pid}/cards/bulk-update", json={"cards": rows})
        check("bulk-update", r.status_code == 200 and r.json()["updated"] == len(cards),
              r.json().get("updated") if r.status_code == 200 else r.text)
        # 列表接口是轻量索引（不含 fields），校验要取详情
        after = [c.get(f"/api/cards/{x['id']}?pid={pid}").json() for x in cards]
        check("批量写入生效", all(x["fields"].get("cost") == 5 for x in after),
              [x["fields"].get("cost") for x in after])

        # 批量删除（卡片 Tab 勾选后一次删掉；不存在的 id 要跳过而不是报错）
        c.post(f"/api/projects/{pid}/cards/import", json={
            "templateId": tid, "format": "csv",
            "payload": "name\n批量删A\n批量删B\n", "mode": "append"})
        tmp_ids = [x["id"] for x in c.get(f"/api/projects/{pid}/cards").json()
                   if x["name"].startswith("批量删")]
        check("批量删除前有目标卡", len(tmp_ids) == 2, len(tmp_ids))
        r = c.post(f"/api/projects/{pid}/cards/bulk-delete",
                   json={"ids": tmp_ids + ["card_not_exist"]})
        check("bulk-delete 返回真实删除数",
              r.status_code == 200 and r.json().get("deleted") == 2,
              r.json() if r.status_code == 200 else r.text[:120])
        left_ids = [x["id"] for x in c.get(f"/api/projects/{pid}/cards").json()]
        check("批量删除后已不存在", not any(i in left_ids for i in tmp_ids), len(left_ids))

        # 数据导出（E3 纯数据）：JSON + CSV
        r = c.get(f"/api/projects/{pid}/cards/export?format=json")
        check("导出 JSON", r.status_code == 200 and len(r.json()["cards"]) == len(cards))
        r = c.get(f"/api/projects/{pid}/cards/export?format=csv")
        csv_text = r.text
        head = csv_text.splitlines()[0]
        check("导出 CSV 表头含 name/cost", "name" in head and "cost" in head, head)
        # 用 csv 解析而不是 splitlines()：字段里可能含换行（卡牌描述就是多行的），
        # 那种情况下 CSV 会把单元格引号包起来，按行数会被多算 → 误报
        import csv as _csv
        import io as _io2
        csv_rows = list(_csv.reader(_io2.StringIO(csv_text)))
        check("CSV 记录数 = 卡数 + 表头", len(csv_rows) == len(cards) + 1,
              f"{len(csv_rows)} vs {len(cards) + 1}")

        # 显式映射导入：把「卡牌名/花费」两列映射到 name/cost
        r = c.post(f"/api/projects/{pid}/cards/import", json={
            "templateId": tid, "format": "csv",
            "payload": "卡牌名,花费\n映射卡A,7\n映射卡B,8\n",
            "mapping": {"卡牌名": "name", "花费": "cost"},
            "mode": "append"})
        check("显式映射导入", r.status_code == 200 and r.json()["created"] == 2,
              r.json().get("created") if r.status_code == 200 else r.text)
        listed = c.get(f"/api/projects/{pid}/cards").json()
        mapped_ids = [x["id"] for x in listed if x["name"].startswith("映射卡")]
        mapped = [c.get(f"/api/cards/{i}?pid={pid}").json() for i in mapped_ids]
        check("映射后卡名与数值正确",
              sorted(x["name"] for x in mapped) == ["映射卡A", "映射卡B"]
              and all(x["fields"]["cost"] in (7, 8) for x in mapped),
              [(x["name"], x["fields"].get("cost")) for x in mapped])
        for x in mapped:
            c.delete(f"/api/cards/{x['id']}?pid={pid}")

        print("[stats]")
        r = c.get(f"/api/projects/{pid}/stats")
        s = r.json()
        check("stats cardCount = 清理后的卡数",
              s["cardCount"] == len(base_cards), s["cardCount"])
        check("有数值分布", len(s["distributions"]) >= 1,
              [(d["label"], len(d["values"])) for d in s["distributions"]])

        print("[assets]")
        r = c.get("/api/asset-libraries")
        libs = r.json()
        check("6 个内置子库", len([l for l in libs if l.get("builtin")]) == 6,
              [(l["id"], l["count"]) for l in libs])
        total_icons = sum(l["count"] for l in libs)
        check("icon 总数 > 20", total_icons > 20, total_icons)
        r = c.get("/api/assets?type=icon&library=elements")
        icons = r.json() if r.status_code == 200 else []
        check("elements 子库有内容", r.status_code == 200 and len(icons) >= 8, len(icons))
        if icons:
            fr = c.get(f"/api/assets/{icons[0]['id']}/file")
            check("icon 文件可读",
                  fr.status_code == 200 and fr.headers["content-type"].startswith("image/"),
                  fr.headers.get("content-type"))
        r = c.get("/api/assets?type=font")
        check("字体清单接口可用", r.status_code == 200 and isinstance(r.json(), list),
              len(r.json()) if r.status_code == 200 else r.text[:80])

        # 自定义字体（bgw_<assetId>）必须能随项目包迁移（G9）。
        # 打包只看字节，所以这里不必是真字形文件。
        print("[字体：自定义字体随项目包迁移（G9）]")
        r = c.post("/api/assets/upload",
                   files={"file": ("smoke_font.ttf", b"\x00\x01\x00\x00" + b"fakettf" * 8,
                                   "font/ttf")},
                   data={"type": "font", "name": "冒烟字体"})
        check("上传字体资源", r.status_code == 200,
              r.text[:120] if r.status_code != 200 else "")
        font_asset = r.json() if r.status_code == 200 else None
        font_fam = ""
        if font_asset:
            font_fam = "bgw_" + font_asset["id"][3:]      # familyOf(): bgw_<id 去掉 as_ 前缀>
            font_fields = [dict(f) for f in tpls[0]["fields"]]
            font_fields[0]["style"] = {**(font_fields[0].get("style") or {}),
                                       "fontFamily": font_fam}
            rr = c.put(f"/api/templates/{tid}", json={"projectId": pid, "fields": font_fields})
            check("模板用上自定义字体", rr.status_code == 200
                  and rr.json()["fields"][0]["style"]["fontFamily"] == font_fam)

        # 缩略图：上传图片时顺手生成（列表页不该拉原图）。
        # 用程序生成一张纯色 PNG —— 只验尺寸/类型/联动，不依赖任何外部素材。
        print("[缩略图]")
        import io as _io
        from PIL import Image as _PILImage
        _buf = _io.BytesIO()
        _PILImage.new("RGB", (600, 400), (12, 34, 56)).save(_buf, "PNG")
        png_bytes = _buf.getvalue()
        r = c.post("/api/assets/upload",
                   files={"file": ("smoke_thumb.png", png_bytes, "image/png")},
                   data={"type": "image", "name": "冒烟缩略图"})
        check("上传图片资源", r.status_code == 200,
              r.text[:120] if r.status_code != 200 else "")
        thumb_aid = r.json()["id"] if r.status_code == 200 else ""
        if thumb_aid:
            t = c.get(f"/api/assets/{thumb_aid}/thumb")
            check("缩略图可读且是 JPEG",
                  t.status_code == 200 and t.headers["content-type"].startswith("image/jpeg"),
                  t.headers.get("content-type"))
            try:
                tsize = _PILImage.open(_io.BytesIO(t.content)).size
            except Exception:
                tsize = (0, 0)
            check("缩略图被压到 480 以内", max(tsize) <= 480, tsize)
            check("原图仍是 600×400 未被改写",
                  _PILImage.open(_io.BytesIO(c.get(f"/api/assets/{thumb_aid}/file").content)).size
                  == (600, 400))
            c.delete(f"/api/assets/{thumb_aid}")
            check("删除资源后缩略图也随之 404",
                  c.get(f"/api/assets/{thumb_aid}/thumb").status_code == 404)

        print("[M3 项目包导出 / 导入（E3）]")
        r = c.get(f"/api/projects/{pid}/export/package")
        check("导出项目包", r.status_code == 200
              and r.headers["content-type"] == "application/zip",
              r.headers.get("content-type"))
        blob = r.content
        import zipfile as _zf
        import io as _io
        with _zf.ZipFile(_io.BytesIO(blob)) as z:
            names = z.namelist()
            manifest = _zf.ZipFile(_io.BytesIO(blob)).read("manifest.json")
        import json as _json
        mf = _json.loads(manifest)
        check("包内含 manifest.json / project.json / 模板 / 卡牌",
              "manifest.json" in names and "project.json" in names
              and any(n.startswith("templates/") for n in names)
              and any(n.startswith("cards/") for n in names), len(names))
        check("manifest 含 schemaVersion 与资源清单",
              mf.get("schemaVersion") == 1 and "assets" in mf,
              {k: mf.get(k) for k in ("templates", "cards")})
        check("manifest 卡数 = 实际卡数", mf.get("cards") == len(cards), mf.get("cards"))
        check("无缺失资源", not mf.get("missingAssets"), mf.get("missingAssets"))
        # G9：自定义字体（bgw_<id>）此前不在引用扫描范围内，会被漏打包
        if font_asset:
            check("字体进了资源清单",
                  any(a.get("id") == font_asset["id"] for a in mf["assets"]),
                  [a.get("id") for a in mf["assets"]])
            check("包内含字体文件",
                  any(n.startswith("assets/fonts/") for n in names),
                  [n for n in names if "fonts" in n])

        # 模拟"另一台机器"：本地先删掉该字体，导入包里应当能把它带回来
        if font_asset:
            check("删除本地字体（模拟换机）",
                  c.delete(f"/api/assets/{font_asset['id']}").status_code == 200)
            check("本地已无该字体",
                  not any(a["id"] == font_asset["id"]
                          for a in c.get("/api/assets?type=font").json()))

        # 再导入回来（rename 策略），验证闭环与 DNA 还原
        r = c.post("/api/projects/import-package",
                   files={"file": ("pkg.zip", blob, "application/zip")})
        check("导入项目包", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
        if r.status_code == 200:
            imported = r.json()
            back_pid = imported["id"]
            check("导入后卡数一致", imported["cardCount"] == len(cards),
                  imported["cardCount"])
            check("导入后模板数一致", imported["templateCount"] >= 1,
                  imported["templateCount"])
            check("导入无缺失资源", not imported["missingAssets"],
                  imported["missingAssets"])
            back_cards = c.get(f"/api/projects/{back_pid}/cards").json()
            check("导入项目可列出卡牌", len(back_cards) == len(cards), len(back_cards))
            if font_asset:
                # 跨机还原：字体文件要回来、模板引用要还在（M3 DoD 的关键一项）
                check("跨机导入：字体资源已恢复",
                      any(a["id"] == font_asset["id"]
                          for a in c.get("/api/assets?type=font").json()))
                fr = c.get(f"/api/assets/{font_asset['id']}/file")
                check("跨机导入：字体文件可读",
                      fr.status_code == 200 and len(fr.content) > 0, fr.status_code)
                back_tpls = c.get(f"/api/projects/{back_pid}/templates").json()
                # 按 id 找，别假定顺序（导入后目录 mtime 顺序会变）
                back = next((t for t in back_tpls if t["id"] == tid), None)
                check("跨机导入：模板仍引用该字体",
                      bool(back)
                      and back["fields"][0]["style"].get("fontFamily") == font_fam,
                      (back or {}).get("fields", [{}])[0].get("style", {}).get("fontFamily"))
            c.delete(f"/api/projects/{back_pid}")

        # conflict=cancel：存在同名项目时应直接 409，而不是静默覆盖
        before = len(c.get("/api/projects").json())
        r = c.post("/api/projects/import-package?conflict=cancel",
                   files={"file": ("pkg.zip", blob, "application/zip")})
        check("同名 cancel 返回 409", r.status_code == 409, r.status_code)
        check("cancel 不会新建项目", len(c.get("/api/projects").json()) == before)

        print("[cleanup]")
        # 还原模板字段（去掉临时字体）并删掉临时字体资源，保证可重复运行
        if font_fam:
            c.put(f"/api/templates/{tid}",
                  json={"projectId": pid, "fields": tpls[0]["fields"]})
            check("还原模板字体", c.get(f"/api/templates/{tid}?pid={pid}").json()
                  ["fields"][0]["style"].get("fontFamily") != font_fam)
        if font_asset:
            check("删除临时字体资源",
                  c.delete(f"/api/assets/{font_asset['id']}").status_code == 200)
        if new_pid:
            check("delete temp project", c.delete(f"/api/projects/{new_pid}").status_code == 200)
    finally:
        # 无论如何都要把用户数据还原（跑崩了也一样）
        if backup and pid:
            _restore_user_data(c, pid, backup)
        c.__exit__(None, None, None)

    dt = (time.perf_counter() - t0) * 1000
    print(f"\n耗时 {dt:.0f} ms | 结果: {'全部通过' if ok else '存在失败: ' + ', '.join(_failed)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
