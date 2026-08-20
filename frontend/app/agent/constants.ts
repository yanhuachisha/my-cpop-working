import { BrainCircuit, ChartNoAxesCombined, Compass, Heart } from "lucide-react";

export const SOURCE_LABELS: Record<string, string> = {
  search_music: "联网音乐搜索",
  recommend_music: "个性化推荐",
  query_listener_memory: "用户音乐记忆",
  query_listening_history: "听歌历史",
  daily_recommendation: "今日推荐",
  hybrid_recommendation: "偏好算法",
  listener_emotion_memory: "情绪记忆",
  listener_preference_profile_tool: "长期偏好",
  weekly_listening_report: "听歌复盘",
};

export const QUICK_ACTIONS = [
  { icon: Compass, label: "推荐一首", prompt: "结合今天的天气、时间和我的听歌记录，只推荐一首现在最适合听的歌，并说明理由。" },
  { icon: BrainCircuit, label: "情绪记忆", prompt: "分析我最近 14 天的听歌情绪、循环和切歌行为，告诉我最近处于什么状态。" },
  { icon: ChartNoAxesCombined, label: "本周复盘", prompt: "生成我的本周听歌复盘，概括播放时段、循环歌曲和情绪变化。" },
  { icon: Heart, label: "理解偏爱", prompt: "结合我的收藏和播放记录，分析我最近真正偏爱的歌手、风格与情绪。" },
] as const;
