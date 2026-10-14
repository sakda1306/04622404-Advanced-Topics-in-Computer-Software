"""
D5 (Could) — คณิตศาสตร์ของ Poisson model สำหรับทำนายผลนัด

ฟังก์ชันในไฟล์นี้เป็น "pure function" ล้วน ๆ ไม่พึ่งข้อมูลจากที่ไหน — รับค่าเฉลี่ยประตูมาแล้วคำนวณ
ความน่าจะเป็นแพ้/ชนะ/เสมอ · ตั้งแต่ CONTRACT v1.7 ข้อมูลความแข็งของทีมและค่าเฉลี่ยลีกมาจาก 07
(football-data) ผ่าน /local/predict และ /local/simulate
"""
import math
from dataclasses import dataclass

# ค่าเฉลี่ยประตูต่อนัดของพรีเมียร์ลีกโดยรวม (baseline) ใช้ตอนทีมใดทีมหนึ่งไม่มีข้อมูลพอ
LEAGUE_AVG_GOALS_PER_MATCH = 1.35

# แต้มต่อความได้เปรียบเจ้าบ้าน (home advantage) แบบคูณเข้ากับ expected goals ของทีมเหย้า
HOME_ADVANTAGE_FACTOR = 1.15

MAX_GOALS = 8  # ตัดหางการแจกแจงที่ N ประตู (ความน่าจะเป็นเกิน 8-0 ต่ำมากจนไม่มีนัยสำคัญ)


@dataclass
class TeamStrength:
    """สรุปฟอร์มของทีมจากผลนัดล่าสุด (จะมาจาก 07 ในอนาคต)"""

    attack_goals_per_match: float  # ยิงได้เฉลี่ยกี่ลูกต่อนัด
    defense_goals_conceded_per_match: float  # เสียเฉลี่ยกี่ลูกต่อนัด
    matches_used: int


def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) เมื่อ X ~ Poisson(lam)"""
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def expected_goals(
    attacking: TeamStrength,
    defending: TeamStrength,
    is_home: bool,
    league_avg: float = LEAGUE_AVG_GOALS_PER_MATCH,
) -> float:
    """
    Expected goals ของทีมหนึ่ง = ความเก่งเกมรุกของทีมนี้ × ความอ่อนเกมรับของอีกฝั่ง เทียบค่าเฉลี่ยลีก
    แล้วคูณ home advantage ถ้าเป็นทีมเหย้า · league_avg มาจาก 07 (ผสมฤดูกาลก่อน + ฤดูกาลนี้)
    """
    attack_strength = attacking.attack_goals_per_match / league_avg
    defense_weakness = defending.defense_goals_conceded_per_match / league_avg
    xg = attack_strength * defense_weakness * league_avg
    if is_home:
        xg *= HOME_ADVANTAGE_FACTOR
    return max(xg, 0.05)  # กันค่าติดลบ/ศูนย์ที่ทำให้ Poisson พัง


def match_outcome_probabilities(
    home: TeamStrength, away: TeamStrength, league_avg: float = LEAGUE_AVG_GOALS_PER_MATCH
) -> dict:
    """
    คำนวณ P(home win), P(draw), P(away win) ด้วย Independent Poisson model:
    สมมติจำนวนประตูของสองทีมเป็นอิสระต่อกัน แจกแจงแบบ Poisson แยกกัน
    แจกแจงร่วม = คูณกัน แล้วรวมตามเงื่อนไขบ้าน > เยือน / เท่ากัน / บ้าน < เยือน
    และเก็บคู่สกอร์ที่ความน่าจะเป็นร่วมสูงสุดไว้เป็น most_likely_score
    """
    home_xg = expected_goals(home, away, is_home=True, league_avg=league_avg)
    away_xg = expected_goals(away, home, is_home=False, league_avg=league_avg)

    home_win = draw = away_win = 0.0
    best, best_p = (0, 0), -1.0
    for h in range(MAX_GOALS + 1):
        p_h = _poisson_pmf(h, home_xg)
        for a in range(MAX_GOALS + 1):
            joint = p_h * _poisson_pmf(a, away_xg)
            if joint > best_p:
                best, best_p = (h, a), joint
            if h > a:
                home_win += joint
            elif h == a:
                draw += joint
            else:
                away_win += joint

    total = home_win + draw + away_win  # ควรใกล้ 1.0 อยู่แล้ว แต่ normalize กันหางที่ตัดทิ้งไป
    return {
        "home_win": round(home_win / total, 4),
        "draw": round(draw / total, 4),
        "away_win": round(away_win / total, 4),
        "home_xg": round(home_xg, 3),
        "away_xg": round(away_xg, 3),
        "most_likely_score": {"home": best[0], "away": best[1]},
    }


def format_percent(p: float) -> str:
    """0.4849 → "48%" · ค่ามากกว่า 0 ที่ปัดแล้วเป็น 0 → "<1%" """
    rounded = round(p * 100)
    if p > 0 and rounded == 0:
        return "<1%"
    return f"{rounded}%"
