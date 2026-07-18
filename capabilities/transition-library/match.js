/*
 * 灵剪 · 转场内容匹配器（Transition Matcher）
 * ---------------------------------------------------------------
 * 「按用户内容匹配对应效果」的落点：不是给每个镜间随机撒转场，而是按
 *   ① 相邻镜能量差 ΔE   ② 语义关系（转折/递进/并列/对比/收束/呼应）
 *   ③ 母题承接（有无共同视觉元素）   ④ 风格（东方/编辑…）
 * 荐出转场，并**强制强转场稀缺**（全片强转场 ≤ 配额，只压能量拐点）——
 * 这是防「均匀撒花哨转场 = AI 味」的核心护栏。
 *
 * 产出 transitionIn/Out 直接喂导演板（director-board），用户可在关卡改。
 *
 * 用法：
 *   var plan = planTransitions(shots, { library: TRANSITIONS, maxStrong: 3, style: '编辑风' });
 *   // plan[i] = { fromN, toN, ref, name, why, energy, downgraded }
 * 单对：matchTransition(shotA, shotB, { library, relation, motifLink, style })
 *
 * shots：至少含 { n, energy }；可选 { relationToNext, motifToNext }。
 * 确定性：无 Date.now / Math.random。
 */
(function (global) {
  'use strict';

  var STRONG = 4; // energy≥STRONG 视为强转场

  function byId(library, id) {
    var list = (library && library.transitions) || [];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  }
  function pick(library, id, why) {
    var t = byId(library, id);
    return {
      ref: id,
      name: t ? t.name : id,
      energy: t ? t.energy : 0,
      why: why
    };
  }

  // 无显式 relation 时，从能量差粗推关系
  function inferRelation(dE) {
    if (dE >= 3) return 'rise';      // 大幅上升 → 冲/甩
    if (dE <= -3) return 'drop';     // 大幅下降 → 反差断点
    if (dE > 0) return 'advance';    // 微升 → 递进
    if (dE < 0) return 'ease';       // 微降 → 舒缓
    return 'parallel';               // 平 → 并列
  }

  /**
   * 单个镜间的首选转场（未施加稀缺配额）。
   */
  function matchTransition(a, b, opts) {
    opts = opts || {};
    var lib = opts.library, style = opts.style || '';
    var dE = (b.energy || 0) - (a.energy || 0);
    var rel = opts.relation || b.relationToPrev || a.relationToNext || inferRelation(dE);
    var motif = opts.motifLink != null ? opts.motifLink : !!a.motifToNext;
    var eastern = /东方|水墨|传统|中国/.test(style);

    // —— 规则优先级（先命中先返回）——
    // 0. 冲进能量顶峰（进入 energy=5 的镜且上升）：优先急推，无论 relation
    if ((b.energy || 0) >= 5 && dE > 0) return pick(lib, 'zoom-punch', '冲进能量顶峰，急推强调');
    // 1. 语义转折 / 大幅升：甩镜
    if (rel === '转折' || rel === 'rise') return pick(lib, 'whip-pan', '语义转折 + 能量上升，甩镜带走');
    // 2. 顶峰跌落：闪黑反差喘息
    if (rel === 'drop' || (dE <= -3 && (a.energy || 0) >= STRONG)) {
      return pick(lib, 'flash-black', '从顶峰猛切到静，反差喘息');
    }
    // 3. 收束 / 东方风：水墨擦除
    if (rel === '收束' || rel === 'ease' && eastern) {
      return pick(lib, 'ink-wipe', eastern ? '东方母题 + 收束，水墨晕染' : '收束章节，晕染擦除');
    }
    // 4. 母题承接：匹配剪辑（隐形而有力）
    if (motif) return pick(lib, 'match-cut', '母题承接，构图对齐匹配剪辑');
    // 5. 递进：推
    if (rel === '递进' || rel === 'advance') return pick(lib, 'push', '叙事递进，推进新层级');
    // 6. 并列：滑移（弱）或硬切
    if (rel === '并列' || rel === 'parallel') return pick(lib, 'hard-cut', '并列内容，隐形硬切');
    // 7. 舒缓下降：溶解（仅慢段；快节奏 Profile 由稀缺守卫兜底降级）
    if (rel === 'ease') return pick(lib, 'dissolve', '舒缓下降，柔性溶解');
    // 默认：隐形硬切
    return pick(lib, 'hard-cut', '默认隐形接续');
  }

  /**
   * 整片规划：逐对匹配 + 强制强转场稀缺（只保留 |ΔE| 最大的 maxStrong 处为强转场，
   * 其余强候选降级为隐形 match-cut / hard-cut）。
   */
  function planTransitions(shots, opts) {
    opts = opts || {};
    var lib = opts.library, maxStrong = opts.maxStrong == null ? 3 : opts.maxStrong;
    shots = shots || [];
    var pairs = [];
    for (var i = 0; i < shots.length - 1; i++) {
      var a = shots[i], b = shots[i + 1];
      var rec = matchTransition(a, b, { library: lib, style: opts.style,
        relation: opts.relations ? opts.relations[i] : undefined,
        motifLink: opts.motifLinks ? opts.motifLinks[i] : undefined });
      pairs.push({ fromN: a.n, toN: b.n, rec: rec, dE: (b.energy || 0) - (a.energy || 0), motif: !!a.motifToNext });
    }
    // 找强转场配额：按 |ΔE| 降序取前 maxStrong 的下标
    var strongIdx = pairs
      .map(function (p, i) { return { i: i, mag: Math.abs(p.dE), isStrong: p.rec.energy >= STRONG }; })
      .filter(function (x) { return x.isStrong; })
      .sort(function (x, y) { return y.mag - x.mag; })
      .slice(0, maxStrong)
      .reduce(function (set, x) { set[x.i] = true; return set; }, {});

    return pairs.map(function (p, i) {
      var rec = p.rec, downgraded = false;
      if (rec.energy >= STRONG && !strongIdx[i]) {
        // 超配额的强转场 → 降级隐形
        rec = p.motif
          ? pick(lib, 'match-cut', '（强转场配额已满，降级）母题承接匹配剪辑')
          : pick(lib, 'hard-cut', '（强转场配额已满，降级）隐形硬切');
        downgraded = true;
      }
      return { fromN: p.fromN, toN: p.toN, ref: rec.ref, name: rec.name, why: rec.why, energy: rec.energy, downgraded: downgraded };
    });
  }

  var api = { matchTransition: matchTransition, planTransitions: planTransitions, STRONG: STRONG };
  global.LJTransitionMatch = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof window !== 'undefined' ? window : this);
