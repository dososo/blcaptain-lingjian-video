/*
 * 转场匹配器回归测试：喂本片 7 镜能量 + 语义标注，planTransitions 应重现
 * 导演板的 6 个转场编排。证明「按内容匹配转场」逻辑自洽。
 * 跑：node capabilities/transition-library/test/match.test.js
 */
const lib = require('../transitions.json');
const { planTransitions } = require('../match.js');

const shots = [
  { n: 1, energy: 4, relationToNext: '转折' },
  { n: 2, energy: 2, motifToNext: true },   // 场记板→模板：母题承接
  { n: 3, energy: 3, relationToNext: '递进' },
  { n: 4, energy: 4 },                        // 进入顶峰 gates(5) → 自动急推
  { n: 5, energy: 5 },                        // 顶峰跌落 → 自动闪黑
  { n: 6, energy: 2, relationToNext: '收束' },
  { n: 7, energy: 3 }
];
const relations = shots.slice(0, -1).map(s => s.relationToNext);
const motifLinks = shots.slice(0, -1).map(s => !!s.motifToNext);

const plan = planTransitions(shots, { library: lib, relations, motifLinks, style: '编辑风', maxStrong: 3 });
const got = plan.map(p => p.ref).join(',');
const want = 'whip-pan,match-cut,push,zoom-punch,flash-black,ink-wipe';

plan.forEach(p => console.log(`  ${p.fromN}→${p.toN}  ${String(p.ref).padEnd(12)} (e${p.energy}) ${p.downgraded ? '[降级]' : ''}  ${p.why}`));

if (got !== want) {
  console.error('\n❌ 不一致\n  实得: ' + got + '\n  期望: ' + want);
  process.exit(1);
}
// 稀缺校验：强转场(e≥4) 数量 ≤ 配额 3
const strong = plan.filter(p => p.energy >= 4).length;
if (strong > 3) { console.error('❌ 强转场超配额: ' + strong); process.exit(1); }
console.log(`\n✅ 重现导演板编排；强转场 ${strong}/3（稀缺守卫生效）`);
