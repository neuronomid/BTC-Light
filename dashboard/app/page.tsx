"use client";

import { useState, useEffect, useCallback } from "react";
import { api, SystemStatus, Position, TradeHistory, WalletBalance, ChartPoint, StatisticalSnapshot } from "@/lib/api";
import { useWebSocket } from "@/lib/use-websocket";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Tooltip as HelpTooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Play,
  Pause,
  Square,
  RotateCcw,
  TrendingUp,
  Wallet,
  Activity,
  BarChart3,
  Cpu,
  LogOut,
  ArrowUpRight,
  ArrowDownRight,
  DollarSign,
  Clock,
  Zap,
  AlertTriangle,
  CheckCircle2,
  CircleHelp,
  ChartCandlestick,
  ChartSpline,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ChartTooltip,
  ResponsiveContainer,
} from "recharts";

function formatCurrency(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

function formatPct(n: number) {
  return `${n >= 0 ? "+" : ""}${(n * 100).toFixed(2)}%`;
}

function parseApiDate(value: string | null) {
  const raw = (value || "").trim();
  if (!raw) return new Date(NaN);
  const normalized = raw.includes("T") ? raw : raw.replace(" ", "T");
  const hasTimeZone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return new Date(hasTimeZone ? normalized : `${normalized}Z`);
}

function timeAgo(iso: string | null) {
  if (!iso) return "—";
  const timestamp = parseApiDate(iso).getTime();
  if (!Number.isFinite(timestamp)) return "—";
  const diff = Date.now() - timestamp;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function Dashboard() {
  const { connected, lastMessage } = useWebSocket();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [openPositions, setOpenPositions] = useState<Position[]>([]);
  const [tradeHistory, setTradeHistory] = useState<TradeHistory | null>(null);
  const [wallet, setWallet] = useState<WalletBalance | null>(null);
  const [chartData, setChartData] = useState<ChartPoint[]>([]);
  const [stats, setStats] = useState<StatisticalSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("overview");
  const [fetchExternal, setFetchExternal] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, op, th, w, cd, st] = await Promise.all([
        api.status(),
        api.openPositions(),
        api.closedTrades(20),
        api.walletBalance(),
        api.chartData("BTC-USD", 168, "4h"),
        api.statistics(),
      ]);
      setStatus(s);
      setOpenPositions(op);
      setTradeHistory(th);
      setWallet(w);
      setChartData(cd);
      setStats(st);
    } catch (e) {
      console.error("Refresh error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const refreshTimeout = window.setTimeout(() => {
      void refresh();
    }, 0);
    const interval = window.setInterval(() => {
      void refresh();
    }, 5000);
    return () => {
      window.clearTimeout(refreshTimeout);
      window.clearInterval(interval);
    };
  }, [refresh]);

  useEffect(() => {
    if (!lastMessage) return;
    if (
      lastMessage.type === "position:opened" ||
      lastMessage.type === "position:closed" ||
      lastMessage.type === "system:start" ||
      lastMessage.type === "system:pause" ||
      lastMessage.type === "system:resume" ||
      lastMessage.type === "system:shutdown" ||
      lastMessage.type === "wallet:deposit" ||
      lastMessage.type === "wallet:withdraw" ||
      lastMessage.type === "candles:new" ||
      lastMessage.type === "statistical:snapshot"
    ) {
      const refreshTimeout = window.setTimeout(() => {
        void refresh();
      }, 0);
      return () => window.clearTimeout(refreshTimeout);
    }
  }, [lastMessage, refresh]);

  const handleAction = async (action: string) => {
    setActionLoading(action);
    try {
      switch (action) {
        case "start":
          await api.start({ fetch_external: fetchExternal });
          break;
        case "pause":
          await api.pause();
          break;
        case "resume":
          await api.resume();
          break;
        case "shutdown":
          await api.shutdown();
          break;
        case "reset":
          await api.reset();
          break;
      }
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setActionLoading(null);
    }
  };

  const totalReturn = status
    ? ((status.equity - status.starting_equity) / status.starting_equity)
    : 0;

  const chartWithMarkers = chartData.map((d) => ({
    ...d,
    time: parseApiDate(d.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    date: parseApiDate(d.timestamp).toLocaleDateString([], { month: "short", day: "numeric" }),
  }));
  const displayedFetchExternal = status?.running || status?.paused
    ? status.fetch_external
    : fetchExternal;

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100">
      {/* Sidebar */}
      <aside className="w-64 border-r border-zinc-800 bg-zinc-900/50 flex flex-col">
        <div className="p-6">
          <h1 className="text-lg font-semibold tracking-tight text-white flex items-center gap-2">
            <Zap className="w-5 h-5 text-amber-400" />
            BTC Trader
          </h1>
          <p className="text-xs text-zinc-500 mt-1">Statistical-LLM Hybrid</p>
        </div>
        <nav className="flex-1 px-3 space-y-1">
          {[
            { id: "overview", label: "Overview", icon: Activity },
            { id: "positions", label: "Positions", icon: BarChart3 },
            { id: "chart", label: "Live Chart", icon: TrendingUp },
            { id: "agents", label: "Agents", icon: Cpu },
            { id: "wallet", label: "Paper Wallet", icon: Wallet },
            { id: "logs", label: "System Logs", icon: LogOut },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === item.id
                  ? "bg-zinc-800 text-white"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/50"
              }`}
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-zinc-800">
          <div className="flex items-center gap-2 text-xs text-zinc-500">
            <div className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-500" : "bg-red-500"}`} />
            {connected ? "Live" : "Disconnected"}
          </div>
          <div className="text-xs text-zinc-600 mt-1">Mode: PAPER</div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-hidden flex flex-col">
        {/* Header */}
        <header className="h-16 border-b border-zinc-800 flex items-center justify-between px-6 bg-zinc-900/30">
          <div className="flex items-center gap-4">
            <Badge
              variant={status?.running ? "default" : "secondary"}
              className={status?.running ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" : "bg-zinc-800 text-zinc-400"}
            >
              {status?.running ? "Running" : status?.paused ? "Paused" : "Stopped"}
            </Badge>
            {status?.current_price && (
              <span className="text-sm font-mono text-zinc-300">
                BTC {formatCurrency(status.current_price)}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <label className={`flex h-7 items-center gap-2 rounded-md border border-zinc-800 px-2 text-xs ${
              status?.running || status?.paused
                ? "text-zinc-500"
                : "text-zinc-300 hover:bg-zinc-800/50"
            }`}>
              <input
                type="checkbox"
                checked={displayedFetchExternal}
                onChange={(event) => setFetchExternal(event.target.checked)}
                disabled={status?.running || status?.paused || !!actionLoading}
                className="h-3.5 w-3.5 accent-emerald-500"
              />
              External feeds
            </label>
            {!status?.running && !status?.paused && (
              <Button
                size="sm"
                onClick={() => handleAction("start")}
                disabled={!!actionLoading}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <Play className="w-4 h-4 mr-1" />
                Start
              </Button>
            )}
            {status?.running && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleAction("pause")}
                disabled={!!actionLoading}
                className="border-amber-500/30 text-amber-400 hover:bg-amber-500/10"
              >
                <Pause className="w-4 h-4 mr-1" />
                Pause
              </Button>
            )}
            {status?.paused && (
              <Button
                size="sm"
                onClick={() => handleAction("resume")}
                disabled={!!actionLoading}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <Play className="w-4 h-4 mr-1" />
                Resume
              </Button>
            )}
            {(status?.running || status?.paused) && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleAction("shutdown")}
                disabled={!!actionLoading}
                className="border-red-500/30 text-red-400 hover:bg-red-500/10"
              >
                <Square className="w-4 h-4 mr-1" />
                Shutdown
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              onClick={() => handleAction("reset")}
              disabled={!!actionLoading}
              className="text-zinc-400 hover:text-zinc-100"
            >
              <RotateCcw className="w-4 h-4" />
            </Button>
          </div>
        </header>

        {/* Content */}
        <ScrollArea className="flex-1">
          <div className="p-6 max-w-7xl mx-auto">
            {loading ? (
              <div className="flex items-center justify-center h-64 text-zinc-500">
                <Activity className="w-5 h-5 animate-spin mr-2" />
                Loading...
              </div>
            ) : (
              <>
                {activeTab === "overview" && (
                  <OverviewTab
                    status={status}
                    openPositions={openPositions}
                    tradeHistory={tradeHistory}
                    totalReturn={totalReturn}
                    stats={stats}
                  />
                )}
                {activeTab === "positions" && (
                  <PositionsTab openPositions={openPositions} tradeHistory={tradeHistory} />
                )}
                {activeTab === "chart" && (
                  <ChartTab chartData={chartWithMarkers} openPositions={openPositions} tradeHistory={tradeHistory} />
                )}
                {activeTab === "agents" && <AgentsTab stats={stats} />}
                {activeTab === "wallet" && <WalletTab wallet={wallet} onRefresh={refresh} />}
                {activeTab === "logs" && <LogsTab />}
              </>
            )}
          </div>
        </ScrollArea>
      </main>
    </div>
  );
}

// --- Overview Tab ---

function OverviewTab({
  status,
  openPositions,
  tradeHistory,
  totalReturn,
  stats,
}: {
  status: SystemStatus | null;
  openPositions: Position[];
  tradeHistory: TradeHistory | null;
  totalReturn: number;
  stats: StatisticalSnapshot | null;
}) {
  return (
    <div className="space-y-6">
      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Equity"
          value={formatCurrency(status?.equity || 0)}
          subtitle={`Starting: ${formatCurrency(status?.starting_equity || 0)}`}
          icon={Wallet}
          trend={totalReturn}
        />
        <StatCard
          title="Daily P&L"
          value={formatCurrency(status?.daily_pnl || 0)}
          subtitle="Today"
          icon={Activity}
          trend={status?.daily_pnl ? status.daily_pnl / (status?.equity || 1) : 0}
        />
        <StatCard
          title="Weekly P&L"
          value={formatCurrency(status?.weekly_pnl || 0)}
          subtitle="This week"
          icon={BarChart3}
          trend={status?.weekly_pnl ? status.weekly_pnl / (status?.equity || 1) : 0}
        />
        <StatCard
          title="Total Return"
          value={formatPct(totalReturn)}
          subtitle={`${tradeHistory?.win_count || 0}W / ${tradeHistory?.loss_count || 0}L`}
          icon={TrendingUp}
          trend={totalReturn}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Open Positions */}
        <Card className="lg:col-span-2 bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <Zap className="w-4 h-4 text-amber-400" />
              Open Positions ({openPositions.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {openPositions.length === 0 ? (
              <div className="text-sm text-zinc-500 py-8 text-center">No open positions</div>
            ) : (
              <div className="space-y-3">
                {openPositions.map((pos) => (
                  <div
                    key={pos.trade_id}
                    className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50"
                  >
                    <div className="flex items-center gap-3">
                      <Badge
                        variant="outline"
                        className={
                          pos.action === "LONG"
                            ? "border-emerald-500/30 text-emerald-400"
                            : "border-red-500/30 text-red-400"
                        }
                      >
                        {pos.action}
                      </Badge>
                      <div>
                        <div className="text-sm font-medium text-zinc-200">
                          {pos.symbol} @ {formatCurrency(pos.entry_price)}
                        </div>
                        <div className="text-xs text-zinc-500">
                          Size: {pos.size.toFixed(6)} | Conviction: {pos.conviction}%
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className={`text-sm font-mono font-medium ${pos.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {pos.pnl >= 0 ? "+" : ""}
                        {formatCurrency(pos.pnl)}
                      </div>
                      <div className={`text-xs ${pos.pnl_pct >= 0 ? "text-emerald-500/70" : "text-red-500/70"}`}>
                        {formatPct(pos.pnl_pct)}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Market Regime */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-blue-400" />
              Market Regime
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {stats?.regime ? (
              <>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-400">Current State</span>
                  <Badge variant="outline" className="border-blue-500/30 text-blue-400">
                    {String(stats.regime.current_state || "Unknown")}
                  </Badge>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-zinc-400">Confidence</span>
                  <span className="text-sm font-mono text-zinc-200">
                    {((stats.regime.state_confidence as number) * 100).toFixed(1)}%
                  </span>
                </div>
                <Separator className="bg-zinc-800" />
                {stats?.trend && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-zinc-400">Trend</span>
                      <span className="text-sm text-zinc-200">
                        {String(stats.trend.trend_classification || "—")}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-zinc-400">Hurst</span>
                      <span className="text-sm font-mono text-zinc-200">
                        {(stats.trend.hurst_100 as number)?.toFixed(3) || "—"}
                      </span>
                    </div>
                  </>
                )}
                <Separator className="bg-zinc-800" />
                {stats?.volatility && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-zinc-400">Vol Regime</span>
                      <span className="text-sm text-zinc-200">
                        {String(stats.volatility.vol_regime || "—")}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-zinc-400">GARCH 4H</span>
                      <span className="text-sm font-mono text-zinc-200">
                        {((stats.volatility.garch_forecast_4h as number) * 100)?.toFixed(2)}%
                      </span>
                    </div>
                  </>
                )}
              </>
            ) : (
              <div className="text-sm text-zinc-500 py-4 text-center">No statistical data</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Recent Trades */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-300">Recent Closed Trades</CardTitle>
        </CardHeader>
        <CardContent>
          {tradeHistory && tradeHistory.trades.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {tradeHistory.trades.slice(0, 6).map((t) => (
                <div
                  key={t.trade_id}
                  className="p-3 rounded-lg bg-zinc-800/50 border border-zinc-700/50"
                >
                  <div className="flex items-center justify-between mb-2">
                    <Badge
                      variant="outline"
                      className={
                        t.action === "LONG"
                          ? "border-emerald-500/30 text-emerald-400"
                          : "border-red-500/30 text-red-400"
                      }
                    >
                      {t.action}
                    </Badge>
                    <span className={`text-sm font-mono font-medium ${t.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {t.pnl >= 0 ? "+" : ""}
                      {formatCurrency(t.pnl)}
                    </span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    Entry: {formatCurrency(t.entry_price)} | {timeAgo(t.closed_at)}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-sm text-zinc-500 py-8 text-center">No closed trades yet</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  trend,
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ElementType;
  trend: number;
}) {
  const isPositive = trend >= 0;
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-medium text-zinc-500 uppercase tracking-wider">{title}</span>
          <Icon className="w-4 h-4 text-zinc-600" />
        </div>
        <div className="text-2xl font-semibold text-white tracking-tight">{value}</div>
        <div className="flex items-center gap-2 mt-1">
          {trend !== 0 && (
            <span className={`text-xs font-medium flex items-center gap-0.5 ${isPositive ? "text-emerald-400" : "text-red-400"}`}>
              {isPositive ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
              {formatPct(trend)}
            </span>
          )}
          <span className="text-xs text-zinc-600">{subtitle}</span>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Positions Tab ---

function PositionsTab({
  openPositions,
  tradeHistory,
}: {
  openPositions: Position[];
  tradeHistory: TradeHistory | null;
}) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-500 uppercase">Open Positions</div>
            <div className="text-2xl font-semibold text-white mt-1">{openPositions.length}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-500 uppercase">Total Trades</div>
            <div className="text-2xl font-semibold text-white mt-1">{tradeHistory?.total_count || 0}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-500 uppercase">Win Rate</div>
            <div className="text-2xl font-semibold text-white mt-1">{tradeHistory?.win_rate.toFixed(1) || 0}%</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-xs text-zinc-500 uppercase">Total P&L</div>
            <div className={`text-2xl font-semibold mt-1 ${(tradeHistory?.total_pnl || 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {formatCurrency(tradeHistory?.total_pnl || 0)}
            </div>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="open" className="w-full">
        <TabsList className="bg-zinc-800/50 border border-zinc-700/50">
          <TabsTrigger value="open" className="data-[state=active]:bg-zinc-700">Open</TabsTrigger>
          <TabsTrigger value="closed" className="data-[state=active]:bg-zinc-700">Closed</TabsTrigger>
        </TabsList>
        <TabsContent value="open" className="mt-4">
          {openPositions.length === 0 ? (
            <div className="text-sm text-zinc-500 py-12 text-center">No open positions</div>
          ) : (
            <div className="space-y-3">
              {openPositions.map((pos) => (
                <PositionCard key={pos.trade_id} position={pos} />
              ))}
            </div>
          )}
        </TabsContent>
        <TabsContent value="closed" className="mt-4">
          {tradeHistory && tradeHistory.trades.length > 0 ? (
            <div className="space-y-3">
              {tradeHistory.trades.map((pos) => (
                <PositionCard key={pos.trade_id} position={pos} closed />
              ))}
            </div>
          ) : (
            <div className="text-sm text-zinc-500 py-12 text-center">No closed trades</div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PositionCard({ position, closed = false }: { position: Position; closed?: boolean }) {
  return (
    <div className="p-4 rounded-lg bg-zinc-900/50 border border-zinc-800">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <Badge
            variant="outline"
            className={
              position.action === "LONG"
                ? "border-emerald-500/30 text-emerald-400"
                : "border-red-500/30 text-red-400"
            }
          >
            {position.action}
          </Badge>
          <div>
            <div className="text-sm font-medium text-zinc-200">{position.trade_id}</div>
            <div className="text-xs text-zinc-500">
              {position.symbol} | {timeAgo(position.opened_at)}
            </div>
          </div>
        </div>
        <div className="text-right">
          <div className={`text-sm font-mono font-medium ${position.pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
            {position.pnl >= 0 ? "+" : ""}
            {formatCurrency(position.pnl)}
          </div>
          <div className={`text-xs ${position.pnl_pct >= 0 ? "text-emerald-500/70" : "text-red-500/70"}`}>
            {formatPct(position.pnl_pct)}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-zinc-800">
        <div>
          <div className="text-xs text-zinc-500">Entry</div>
          <div className="text-sm font-mono text-zinc-300">{formatCurrency(position.entry_price)}</div>
        </div>
        <div>
          <div className="text-xs text-zinc-500">Size</div>
          <div className="text-sm font-mono text-zinc-300">{position.size.toFixed(6)}</div>
        </div>
        <div>
          <div className="text-xs text-zinc-500">Stop Loss</div>
          <div className="text-sm font-mono text-red-400/70">{formatCurrency(position.stop_loss)}</div>
        </div>
        <div>
          <div className="text-xs text-zinc-500">Take Profit</div>
          <div className="text-sm font-mono text-emerald-400/70">{formatCurrency(position.take_profit)}</div>
        </div>
      </div>
      {closed && position.exit_reason && (
        <div className="mt-3 text-xs text-zinc-500">
          Exit: <span className="text-zinc-400">{position.exit_reason}</span>
        </div>
      )}
      <div className="mt-3 text-xs text-zinc-600 line-clamp-2">{position.reasoning}</div>
    </div>
  );
}

// --- Chart Tab ---

type ChartDatum = ChartPoint & { time: string; date: string };
type ChartView = "candles" | "curve";
const DEFAULT_CANDLE_DURATION_MS = 4 * 60 * 60 * 1000;

function toFiniteNumber(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function toCandleDatum(point: ChartDatum) {
  const price = toFiniteNumber(point.price, 0);
  const open = toFiniteNumber(point.open, price);
  const close = toFiniteNumber(point.close, price);
  const rawHigh = toFiniteNumber(point.high, Math.max(open, close));
  const rawLow = toFiniteNumber(point.low, Math.min(open, close));
  const high = Math.max(rawHigh, open, close);
  const low = Math.min(rawLow, open, close);

  return {
    ...point,
    price: close,
    open,
    high,
    low,
    close,
    volume: toFiniteNumber(point.volume, 0),
  };
}

function formatAxisPrice(value: number) {
  return `$${(value / 1000).toFixed(1)}k`;
}

function parseTimeframeMs(timeframe: string | null | undefined) {
  const match = (timeframe || "").trim().toLowerCase().match(/^(\d+(?:\.\d+)?)(m|h|d)$/);
  if (!match) return DEFAULT_CANDLE_DURATION_MS;
  const amount = Number(match[1]);
  if (!Number.isFinite(amount) || amount <= 0) return DEFAULT_CANDLE_DURATION_MS;
  const unit = match[2];
  if (unit === "m") return amount * 60 * 1000;
  if (unit === "h") return amount * 60 * 60 * 1000;
  return amount * 24 * 60 * 60 * 1000;
}

function formatCountdown(ms: number) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds].map((part) => String(part).padStart(2, "0")).join(":");
}

function getCandleCloseStatus(chartData: ChartDatum[], nowMs: number) {
  const candles = chartData
    .map(toCandleDatum)
    .filter((c) => c.close > 0 && [c.open, c.high, c.low, c.close].every(Number.isFinite));
  if (candles.length === 0) return null;

  const lastCandle = candles[candles.length - 1];
  const durationMs = parseTimeframeMs(lastCandle.timeframe);
  const startMs = parseApiDate(lastCandle.timestamp).getTime();
  if (!Number.isFinite(startMs)) return null;

  const lastCloseMs = startMs + durationMs;
  const lastCandleIsLive = nowMs >= startMs && nowMs < lastCloseMs;
  const nextCloseMs = lastCandleIsLive
    ? lastCloseMs
    : Math.floor(nowMs / durationMs) * durationMs + durationMs;

  return {
    isLive: lastCandleIsLive,
    countdownLabel: formatCountdown(nextCloseMs - nowMs),
    closeTimeLabel: new Date(nextCloseMs).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
  };
}

function isOpenCandle(candle: ChartDatum, nowMs: number) {
  const startMs = parseApiDate(candle.timestamp).getTime();
  if (!Number.isFinite(startMs)) return false;
  const closeMs = startMs + parseTimeframeMs(candle.timeframe);
  return nowMs >= startMs && nowMs < closeMs;
}

function formatVolume(value: number) {
  if (!Number.isFinite(value)) return "0";
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}

function ChartTab({
  chartData,
  openPositions,
  tradeHistory,
}: {
  chartData: ChartDatum[];
  openPositions: Position[];
  tradeHistory: TradeHistory | null;
}) {
  const [chartView, setChartView] = useState<ChartView>("candles");
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const tradeMarkers = [
    ...(openPositions.map((p) => ({
      time: parseApiDate(p.opened_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      price: p.entry_price,
      type: p.action as string,
      status: "OPEN",
    }))),
    ...(tradeHistory?.trades.map((p) => ({
      time: p.closed_at ? parseApiDate(p.closed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "",
      price: p.entry_price,
      type: p.action as string,
      status: "CLOSED",
      pnl: p.pnl,
    })) || []),
  ];

  const activeTitle = chartView === "candles" ? "Candlestick view" : "Curve view";
  const candleStatus = getCandleCloseStatus(chartData, nowMs);

  return (
    <div className="space-y-6">
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-3 flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-sm font-medium text-zinc-300 flex items-center gap-2">
            {chartView === "candles" ? (
              <ChartCandlestick className="w-4 h-4 text-emerald-400" />
            ) : (
              <TrendingUp className="w-4 h-4 text-blue-400" />
            )}
            BTC Price (4H)
          </CardTitle>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {candleStatus && (
              <div
                className={`inline-flex h-7 items-center gap-2 rounded-md border px-2.5 text-xs ${
                  candleStatus.isLive
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : "border-amber-500/30 bg-amber-500/10 text-amber-300"
                }`}
                title={`Closes at ${candleStatus.closeTimeLabel}`}
              >
                <Clock className="h-3.5 w-3.5" />
                <span className="text-zinc-400">{candleStatus.isLive ? "Closes in" : "Next close"}</span>
                <span className="font-mono tabular-nums text-zinc-100">{candleStatus.countdownLabel}</span>
              </div>
            )}
            <div
              className="inline-flex rounded-lg border border-zinc-800 bg-zinc-950/70 p-0.5"
              role="group"
              aria-label={activeTitle}
            >
              <button
                type="button"
                onClick={() => setChartView("candles")}
                className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors ${
                  chartView === "candles"
                    ? "bg-zinc-800 text-white shadow-sm"
                    : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
                }`}
              >
                <ChartCandlestick className="h-3.5 w-3.5" />
                Candles
              </button>
              <button
                type="button"
                onClick={() => setChartView("curve")}
                className={`inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors ${
                  chartView === "curve"
                    ? "bg-zinc-800 text-white shadow-sm"
                    : "text-zinc-500 hover:bg-zinc-900 hover:text-zinc-200"
                }`}
              >
                <ChartSpline className="h-3.5 w-3.5" />
                Curve
              </button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="h-[400px] w-full">
            {chartView === "candles" ? (
              <CandlestickPriceChart chartData={chartData} nowMs={nowMs} />
            ) : (
              <PriceCurveChart chartData={chartData} />
            )}
          </div>
        </CardContent>
      </Card>

      {/* Trade Markers */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-zinc-300">Trade Activity</CardTitle>
        </CardHeader>
        <CardContent>
          {tradeMarkers.length === 0 ? (
            <div className="text-sm text-zinc-500 py-8 text-center">No trade activity</div>
          ) : (
            <div className="space-y-2">
              {tradeMarkers.slice(0, 20).map((m, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      m.type === "LONG" ? "bg-emerald-500" : "bg-red-500"
                    }`}
                  />
                  <span className="text-zinc-500 w-16">{m.time}</span>
                  <Badge
                    variant="outline"
                    className={
                      m.type === "LONG"
                        ? "border-emerald-500/30 text-emerald-400"
                        : "border-red-500/30 text-red-400"
                    }
                  >
                    {m.type}
                  </Badge>
                  <span className="text-zinc-400">{formatCurrency(m.price)}</span>
                  <Badge
                    variant="outline"
                    className={
                      m.status === "OPEN"
                        ? "border-amber-500/30 text-amber-400"
                        : "border-zinc-600 text-zinc-400"
                    }
                  >
                    {m.status}
                  </Badge>
                  {"pnl" in m && (
                    <span className={`ml-auto font-mono ${(m as {pnl: number}).pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {(m as {pnl: number}).pnl >= 0 ? "+" : ""}
                      {formatCurrency((m as {pnl: number}).pnl)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function PriceCurveChart({ chartData }: { chartData: ChartDatum[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={chartData}>
        <defs>
          <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
        <XAxis dataKey="time" stroke="#52525b" fontSize={12} tickLine={false} />
        <YAxis
          stroke="#52525b"
          fontSize={12}
          tickLine={false}
          domain={["auto", "auto"]}
          tickFormatter={(v: number) => formatAxisPrice(v)}
        />
        <ChartTooltip
          contentStyle={{
            backgroundColor: "#18181b",
            border: "1px solid #27272a",
            borderRadius: "8px",
            fontSize: "12px",
          }}
          labelFormatter={(_, payload) => {
            const point = payload?.[0]?.payload as ChartDatum | undefined;
            return point ? `${point.date} ${point.time}` : "";
          }}
          formatter={(value) => [formatCurrency(Number(value) || 0), "Close"]}
        />
        <Area
          type="monotone"
          dataKey="price"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#priceGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function CandlestickPriceChart({ chartData, nowMs }: { chartData: ChartDatum[]; nowMs: number }) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const candles = chartData
    .map(toCandleDatum)
    .filter((c) => c.close > 0 && c.high >= c.low && [c.open, c.high, c.low, c.close].every(Number.isFinite));

  if (candles.length === 0) {
    return <div className="flex h-full items-center justify-center text-sm text-zinc-500">No candle data</div>;
  }

  const width = 1000;
  const height = 360;
  const plotLeft = 68;
  const plotRight = 18;
  const plotTop = 16;
  const plotBottom = 34;
  const plotWidth = width - plotLeft - plotRight;
  const plotHeight = height - plotTop - plotBottom;
  const rawMin = Math.min(...candles.map((c) => c.low));
  const rawMax = Math.max(...candles.map((c) => c.high));
  const rawRange = rawMax - rawMin || rawMax * 0.01 || 1;
  const minPrice = rawMin - rawRange * 0.08;
  const maxPrice = rawMax + rawRange * 0.08;
  const priceRange = maxPrice - minPrice || 1;
  const candleSpacing = plotWidth / Math.max(candles.length, 1);
  const candleWidth = Math.min(Math.max(candleSpacing * 0.48, 5), 16);
  const xLabelEvery = Math.max(1, Math.ceil(candles.length / 6));
  const yTicks = Array.from({ length: 5 }, (_, i) => maxPrice - (priceRange * i) / 4);
  const lastCandle = candles[candles.length - 1];
  let liveCandleIndex = -1;
  candles.forEach((c, index) => {
    if (isOpenCandle(c, nowMs)) liveCandleIndex = index;
  });

  const xForIndex = (index: number) => {
    if (candles.length === 1) return plotLeft + plotWidth / 2;
    return plotLeft + (plotWidth * index) / (candles.length - 1);
  };

  const yForPrice = (price: number) => plotTop + ((maxPrice - price) / priceRange) * plotHeight;

  const handleMouseMove = (event: React.MouseEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const chartX = ((event.clientX - rect.left) / rect.width) * width;
    const position = Math.min(Math.max(chartX, plotLeft), plotLeft + plotWidth);
    const index =
      candles.length === 1
        ? 0
        : Math.round(((position - plotLeft) / plotWidth) * (candles.length - 1));
    setActiveIndex(Math.min(Math.max(index, 0), candles.length - 1));
  };

  const activeCandle = activeIndex === null ? null : candles[activeIndex];
  const activeX = activeIndex === null ? null : xForIndex(activeIndex);
  const latestY = yForPrice(lastCandle.close);

  return (
    <div className="relative h-full w-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-full w-full"
        role="img"
        aria-label="BTC 4 hour candlestick price chart"
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setActiveIndex(null)}
      >
        <rect x={plotLeft} y={plotTop} width={plotWidth} height={plotHeight} fill="#09090b" opacity={0.35} />
        {yTicks.map((tick) => {
          const y = yForPrice(tick);
          return (
            <g key={tick}>
              <line x1={plotLeft} x2={plotLeft + plotWidth} y1={y} y2={y} stroke="#27272a" strokeDasharray="3 3" />
              <text x={plotLeft - 10} y={y + 4} textAnchor="end" className="fill-zinc-600 text-[12px]">
                {formatAxisPrice(tick)}
              </text>
            </g>
          );
        })}
        <line x1={plotLeft} x2={plotLeft} y1={plotTop} y2={plotTop + plotHeight} stroke="#3f3f46" />
        <line x1={plotLeft} x2={plotLeft + plotWidth} y1={plotTop + plotHeight} y2={plotTop + plotHeight} stroke="#3f3f46" />

        {candles.map((c, index) => {
          const x = xForIndex(index);
          const openY = yForPrice(c.open);
          const closeY = yForPrice(c.close);
          const highY = yForPrice(c.high);
          const lowY = yForPrice(c.low);
          const isUp = c.close >= c.open;
          const isLiveCandle = index === liveCandleIndex;
          const color = isUp ? "#10b981" : "#ef4444";
          const bodyTop = Math.min(openY, closeY);
          const bodyHeight = Math.max(Math.abs(openY - closeY), 2);
          return (
            <g key={`${c.timestamp}-${index}`}>
              {isLiveCandle && (
                <rect
                  x={x - candleWidth * 0.8}
                  y={plotTop + 2}
                  width={candleWidth * 1.6}
                  height={plotHeight - 4}
                  fill={color}
                  opacity={0.08}
                  rx={4}
                />
              )}
              <line x1={x} x2={x} y1={highY} y2={lowY} stroke={color} strokeWidth={isLiveCandle ? 2.25 : 1.5} />
              <rect
                x={x - candleWidth / 2}
                y={bodyTop}
                width={candleWidth}
                height={bodyHeight}
                fill={color}
                stroke={isLiveCandle ? "#e4e4e7" : color}
                strokeWidth={isLiveCandle ? 1.4 : 1}
                rx={1.5}
              />
              {isLiveCandle && (
                <circle cx={x} cy={closeY} r={4.2} fill={color} stroke="#e4e4e7" strokeWidth={1}>
                  <animate attributeName="opacity" values="1;0.35;1" dur="1.4s" repeatCount="indefinite" />
                </circle>
              )}
            </g>
          );
        })}

        {candles.map((c, index) => {
          if (index % xLabelEvery !== 0 && index !== candles.length - 1) return null;
          const x = xForIndex(index);
          return (
            <text key={`x-${c.timestamp}`} x={x} y={height - 8} textAnchor="middle" className="fill-zinc-600 text-[12px]">
              {c.time}
            </text>
          );
        })}

        <line
          x1={plotLeft}
          x2={plotLeft + plotWidth}
          y1={latestY}
          y2={latestY}
          stroke="#71717a"
          strokeDasharray="5 5"
          opacity={0.7}
        />
        <text x={plotLeft + plotWidth - 4} y={latestY - 7} textAnchor="end" className="fill-zinc-400 text-[12px]">
          {formatCurrency(lastCandle.close)}
        </text>

        {activeCandle && activeX !== null && (
          <g>
            <line x1={activeX} x2={activeX} y1={plotTop} y2={plotTop + plotHeight} stroke="#a1a1aa" opacity={0.45} />
            <line
              x1={plotLeft}
              x2={plotLeft + plotWidth}
              y1={yForPrice(activeCandle.close)}
              y2={yForPrice(activeCandle.close)}
              stroke="#a1a1aa"
              opacity={0.35}
            />
          </g>
        )}
        <rect x={plotLeft} y={plotTop} width={plotWidth} height={plotHeight} fill="transparent" />
      </svg>

      {activeCandle && activeX !== null && (
        <div
          className="pointer-events-none absolute z-10 min-w-44 rounded-lg border border-zinc-700 bg-zinc-950/95 px-3 py-2 text-xs shadow-xl shadow-black/30"
          style={{
            left: `${(activeX / width) * 100}%`,
            top: `${Math.min(Math.max((yForPrice(activeCandle.close) / height) * 100, 16), 84)}%`,
            transform:
              activeIndex !== null && activeIndex > candles.length / 2
                ? "translate(calc(-100% - 10px), -50%)"
                : "translate(10px, -50%)",
          }}
        >
          <div className="font-medium text-zinc-200">
            {activeCandle.date} {activeCandle.time}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-zinc-500">
            <span>Open</span>
            <span className="text-right font-mono text-zinc-200">{formatCurrency(activeCandle.open)}</span>
            <span>High</span>
            <span className="text-right font-mono text-emerald-400">{formatCurrency(activeCandle.high)}</span>
            <span>Low</span>
            <span className="text-right font-mono text-red-400">{formatCurrency(activeCandle.low)}</span>
            <span>Close</span>
            <span className="text-right font-mono text-zinc-200">{formatCurrency(activeCandle.close)}</span>
            <span>Volume</span>
            <span className="text-right font-mono text-zinc-300">{formatVolume(activeCandle.volume)}</span>
            {activeIndex === liveCandleIndex && (
              <>
                <span>Status</span>
                <span className="text-right font-mono text-emerald-300">LIVE</span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// --- Agents Tab ---

const AGENT_CARD_HELP = {
  regime: "Shows the market state the stats engine sees right now, such as bear, bull, or sideways.",
  trend: "Summarizes whether price is trending, chopping, or acting close to random.",
  volatility: "Estimates how large BTC price moves may be over the current 4-hour timeframe.",
  tailRisk: "Focuses on rare but large losses. These numbers help the system stay cautious.",
  changePoint: "Looks for signs that the market has shifted into a new behavior pattern.",
  efficiency: "Shows how random or predictable the market looks from recent price patterns.",
  correlation: "Compares BTC with other markets to show whether outside market stress may matter.",
  probability: "Estimates trade odds and position size when a trade setup has been evaluated.",
} as const;

const AGENT_METRIC_HELP = {
  currentState: "The market mode detected now, such as bear trend, bull trend, or sideways.",
  regimeConfidence: "How sure the model is about the current market state. Higher means clearer evidence.",
  expectedDuration: "How many 4-hour candles this state is expected to last. It is an estimate, not a promise.",
  trendClassification: "A simple label for price behavior, like trending, mean-reverting, or random walk.",
  hurst100: "Trend vs chop over the last 100 candles. Above 0.5 leans trending; below 0.5 leans mean-reverting.",
  hurst500: "The same Hurst check over 500 candles, giving a slower, longer-term trend view.",
  adx: "Trend strength only. Below 20 is usually weak; above 25 is stronger. It does not show direction.",
  trendScore: "A combined score for trend strength. Higher means the model sees a stronger trend.",
  garch4h: "A 4-hour volatility forecast from a GARCH model. Higher means larger expected price movement.",
  egarch4h: "Another 4-hour volatility forecast that reacts differently to sharp moves. It is a cross-check.",
  realized1d: "How much BTC actually moved over the last day. This shows recent real volatility.",
  volPercentile: "Current volatility compared with the last 90 days. 0% is quiet; 100% is very volatile.",
  volRegime: "A simple volatility bucket, such as low, normal, or high.",
  var95: "Value at Risk at 95%. A rough 4-hour loss level expected to be exceeded about 1 time out of 20.",
  cvar95: "Average loss when the 95% VaR level is exceeded. It shows how bad the bad tail may be.",
  var99: "A more extreme 4-hour loss level, expected to be exceeded about 1 time out of 100.",
  tailIndex: "Shows how heavy the extreme-loss tail is. Lower values usually mean extreme moves are more likely.",
  tailRiskLevel: "Plain-language summary of tail risk. Higher risk means the system should be more cautious.",
  changeProbability: "Chance that the market recently shifted into a different behavior pattern.",
  lastChange: "How many 4-hour candles have passed since the last detected market shift.",
  cusumBreached: "True means a fast shift detector has triggered, warning that recent moves look unusual.",
  stability: "How stable the current market state looks. Higher means less evidence of a recent shift.",
  recommendHalt: "True means the stats layer recommends pausing trades because conditions may be unstable.",
  shannonEntropy: "Measures how mixed or uncertain recent moves are. Higher means more random behavior.",
  sampleEntropy: "Measures pattern complexity. Higher means recent price patterns repeat less.",
  randomWalkRejected: "True means price did not look like a pure random walk in this test.",
  efficiencyScore: "How hard the market looks to predict. Higher usually means fewer useful patterns.",
  predictability: "A simple label for how predictable the current market looks.",
  btcSpx: "30-day relationship between BTC and the S&P 500. Positive means they moved together.",
  btcDxy: "30-day relationship between BTC and the U.S. dollar index. Negative often means BTC rose when the dollar fell.",
  btcEth: "30-day relationship between BTC and ETH. High positive values mean they moved closely together.",
  tailDependence: "How often BTC and SPX have extreme moves together. Higher means stock-market stress matters more.",
  riskRegime: "A simple macro label, such as risk-on, risk-off, or mixed.",
  probTpBeforeSl: "Estimated chance that take profit is hit before stop loss for the evaluated trade.",
  expectedValue: "Average expected gain or loss after odds and payoff are considered. Positive is better.",
  bayesianLong: "Model-updated probability that a long trade is favored.",
  bayesianShort: "Model-updated probability that a short trade is favored.",
  kellyFraction: "A sizing guide based on edge and payoff. It can be aggressive, so safety rules may cap it.",
  recommendedSize: "Suggested position size as a percent of account equity after sizing logic.",
} as const;

function AgentsTab({ stats }: { stats: StatisticalSnapshot | null }) {
  if (!stats) {
    return (
      <div className="flex items-center justify-center h-64 text-zinc-500">
        <Cpu className="w-5 h-5 animate-spin mr-2" />
        Loading agent data...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <TooltipProvider delay={150}>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Regime */}
        <AgentCard title="Regime Classification" icon={CheckCircle2} color="blue" help={AGENT_CARD_HELP.regime}>
          <DataRow label="Current State" value={String(stats.regime?.current_state || "—")} help={AGENT_METRIC_HELP.currentState} />
          <DataRow label="Confidence" value={`${((stats.regime?.state_confidence as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.regimeConfidence} />
          <DataRow label="Expected Duration" value={`${(stats.regime?.expected_duration_candles as number)?.toFixed(1) || "—"} candles`} help={AGENT_METRIC_HELP.expectedDuration} />
        </AgentCard>

        {/* Trend */}
        <AgentCard title="Trend Strength" icon={TrendingUp} color="emerald" help={AGENT_CARD_HELP.trend}>
          <DataRow label="Classification" value={String(stats.trend?.trend_classification || "—")} help={AGENT_METRIC_HELP.trendClassification} />
          <DataRow label="Hurst (100)" value={(stats.trend?.hurst_100 as number)?.toFixed(3) || "—"} help={AGENT_METRIC_HELP.hurst100} />
          <DataRow label="Hurst (500)" value={(stats.trend?.hurst_500 as number)?.toFixed(3) || "—"} help={AGENT_METRIC_HELP.hurst500} />
          <DataRow label="ADX" value={(stats.trend?.adx as number)?.toFixed(1) || "—"} help={AGENT_METRIC_HELP.adx} />
          <DataRow label="Trend Score" value={`${((stats.trend?.trend_strength_score as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.trendScore} />
        </AgentCard>

        {/* Volatility */}
        <AgentCard title="Volatility Forecast" icon={AlertTriangle} color="amber" help={AGENT_CARD_HELP.volatility}>
          <DataRow label="GARCH 4H" value={`${((stats.volatility?.garch_forecast_4h as number) * 100)?.toFixed(2)}%`} help={AGENT_METRIC_HELP.garch4h} />
          <DataRow label="EGARCH 4H" value={`${((stats.volatility?.egarch_forecast_4h as number) * 100)?.toFixed(2)}%`} help={AGENT_METRIC_HELP.egarch4h} />
          <DataRow label="Realized 1D" value={`${((stats.volatility?.realized_vol_1d as number) * 100)?.toFixed(2)}%`} help={AGENT_METRIC_HELP.realized1d} />
          <DataRow label="Vol Percentile" value={`${((stats.volatility?.vol_percentile_90d as number) * 100).toFixed(0)}%`} help={AGENT_METRIC_HELP.volPercentile} />
          <DataRow label="Regime" value={String(stats.volatility?.vol_regime || "—")} help={AGENT_METRIC_HELP.volRegime} />
        </AgentCard>

        {/* Tail Risk */}
        <AgentCard title="Tail Risk" icon={AlertTriangle} color="red" help={AGENT_CARD_HELP.tailRisk}>
          <DataRow label="VaR 95%" value={`${((stats.tail_risk?.var_95_4h as number) * 100)?.toFixed(2)}%`} help={AGENT_METRIC_HELP.var95} />
          <DataRow label="CVaR 95%" value={`${((stats.tail_risk?.cvar_95_4h as number) * 100)?.toFixed(2)}%`} help={AGENT_METRIC_HELP.cvar95} />
          <DataRow label="VaR 99%" value={`${((stats.tail_risk?.var_99_4h as number) * 100)?.toFixed(2)}%`} help={AGENT_METRIC_HELP.var99} />
          <DataRow label="Tail Index" value={(stats.tail_risk?.tail_index as number)?.toFixed(2) || "—"} help={AGENT_METRIC_HELP.tailIndex} />
          <DataRow label="Risk Level" value={String(stats.tail_risk?.tail_risk_level || "—")} help={AGENT_METRIC_HELP.tailRiskLevel} />
        </AgentCard>

        {/* Change Point */}
        <AgentCard title="Change Point Detection" icon={Clock} color="purple" help={AGENT_CARD_HELP.changePoint}>
          <DataRow label="Change Probability" value={`${((stats.change_point?.bocpd_change_probability as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.changeProbability} />
          <DataRow label="Last Change" value={`${stats.change_point?.last_change_point_candles_ago || "—"} candles ago`} help={AGENT_METRIC_HELP.lastChange} />
          <DataRow label="CUSUM Breached" value={String(stats.change_point?.cusum_breached || false)} help={AGENT_METRIC_HELP.cusumBreached} />
          <DataRow label="Stability" value={`${((stats.change_point?.regime_stability_score as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.stability} />
          <DataRow label="Recommend Halt" value={String(stats.change_point?.recommend_halt || false)} help={AGENT_METRIC_HELP.recommendHalt} />
        </AgentCard>

        {/* Efficiency */}
        <AgentCard title="Market Efficiency" icon={Activity} color="cyan" help={AGENT_CARD_HELP.efficiency}>
          <DataRow label="Shannon Entropy" value={(stats.efficiency?.shannon_entropy as number)?.toFixed(2) || "—"} help={AGENT_METRIC_HELP.shannonEntropy} />
          <DataRow label="Sample Entropy" value={(stats.efficiency?.sample_entropy as number)?.toFixed(2) || "—"} help={AGENT_METRIC_HELP.sampleEntropy} />
          <DataRow label="Random Walk Rejected" value={String(stats.efficiency?.random_walk_rejected || false)} help={AGENT_METRIC_HELP.randomWalkRejected} />
          <DataRow label="Efficiency Score" value={`${((stats.efficiency?.efficiency_score as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.efficiencyScore} />
          <DataRow label="Predictability" value={String(stats.efficiency?.predictability_level || "—")} help={AGENT_METRIC_HELP.predictability} />
        </AgentCard>

        {/* Correlation */}
        <AgentCard title="Correlation" icon={BarChart3} color="orange" help={AGENT_CARD_HELP.correlation}>
          <DataRow label="BTC-SPX (30d)" value={(stats.correlation?.corr_btc_spx_30d as number)?.toFixed(2) || "—"} help={AGENT_METRIC_HELP.btcSpx} />
          <DataRow label="BTC-DXY (30d)" value={(stats.correlation?.corr_btc_dxy_30d as number)?.toFixed(2) || "—"} help={AGENT_METRIC_HELP.btcDxy} />
          <DataRow label="BTC-ETH (30d)" value={(stats.correlation?.corr_btc_eth_30d as number)?.toFixed(2) || "—"} help={AGENT_METRIC_HELP.btcEth} />
          <DataRow label="Tail Dependence" value={`${((stats.correlation?.tail_dependence_btc_spx as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.tailDependence} />
          <DataRow label="Risk Regime" value={String(stats.correlation?.risk_on_off_regime || "—")} help={AGENT_METRIC_HELP.riskRegime} />
        </AgentCard>

        {/* Probability */}
        <AgentCard title="Probability & Sizing" icon={DollarSign} color="green" help={AGENT_CARD_HELP.probability}>
          <DataRow label="P(TP before SL)" value={`${((stats.probability?.prob_hit_tp_before_sl as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.probTpBeforeSl} />
          <DataRow label="Expected Value" value={`${((stats.probability?.expected_value_per_trade as number) * 100).toFixed(2)}%`} help={AGENT_METRIC_HELP.expectedValue} />
          <DataRow label="Bayesian Long" value={`${((stats.probability?.bayesian_posterior_long as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.bayesianLong} />
          <DataRow label="Bayesian Short" value={`${((stats.probability?.bayesian_posterior_short as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.bayesianShort} />
          <DataRow label="Kelly Fraction" value={`${((stats.probability?.kelly_fraction as number) * 100).toFixed(1)}%`} help={AGENT_METRIC_HELP.kellyFraction} />
          <DataRow label="Recommended Size" value={`${((stats.probability?.recommended_size_pct_equity as number) * 100).toFixed(2)}%`} help={AGENT_METRIC_HELP.recommendedSize} />
        </AgentCard>
        </div>
      </TooltipProvider>
    </div>
  );
}

function AgentCard({
  title,
  icon: Icon,
  color,
  help,
  children,
}: {
  title: string;
  icon: React.ElementType;
  color: string;
  help: string;
  children: React.ReactNode;
}) {
  const colorMap: Record<string, string> = {
    blue: "text-blue-400",
    emerald: "text-emerald-400",
    amber: "text-amber-400",
    red: "text-red-400",
    purple: "text-purple-400",
    cyan: "text-cyan-400",
    orange: "text-orange-400",
    green: "text-green-400",
  };
  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className={`text-sm font-medium flex items-center gap-2 ${colorMap[color] || "text-zinc-300"}`}>
          <HelpTooltip>
            <TooltipTrigger
              type="button"
              className="group/help inline-flex items-center gap-2 rounded-md border-0 bg-transparent p-0 text-left text-inherit transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-600"
            >
              <Icon className="w-4 h-4" />
              <span>{title}</span>
              <CircleHelp className="h-3 w-3 text-current opacity-50 transition-opacity group-hover/help:opacity-90 group-focus-visible/help:opacity-90" />
            </TooltipTrigger>
            <TooltipContent
              side="top"
              align="start"
              sideOffset={8}
              className="max-w-72 items-start px-3 py-2 text-left leading-snug"
            >
              {help}
            </TooltipContent>
          </HelpTooltip>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">{children}</CardContent>
    </Card>
  );
}

function DataRow({ label, value, help }: { label: string; value: string; help: string }) {
  return (
    <HelpTooltip>
      <TooltipTrigger
        type="button"
        className="group/help flex w-full items-center justify-between rounded-md border-0 bg-transparent px-1 py-0.5 text-left text-sm transition-colors hover:bg-zinc-800/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-zinc-600"
      >
        <span className="inline-flex min-w-0 items-center gap-1.5 text-zinc-500">
          <span className="truncate">{label}</span>
          <CircleHelp className="h-3 w-3 shrink-0 text-zinc-600 transition-colors group-hover/help:text-zinc-300 group-focus-visible/help:text-zinc-300" />
        </span>
        <span className="ml-4 shrink-0 text-zinc-200 font-mono">{value}</span>
      </TooltipTrigger>
      <TooltipContent
        side="top"
        align="start"
        sideOffset={8}
        className="max-w-72 items-start px-3 py-2 text-left leading-snug"
      >
        {help}
      </TooltipContent>
    </HelpTooltip>
  );
}

// --- Wallet Tab ---

function WalletTab({ wallet, onRefresh }: { wallet: WalletBalance | null; onRefresh: () => void }) {
  const [amount, setAmount] = useState("");
  const [loading, setLoading] = useState(false);

  const handleDeposit = async () => {
    const n = parseFloat(amount);
    if (!n || n <= 0) return;
    setLoading(true);
    try {
      await api.deposit(n);
      setAmount("");
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleWithdraw = async () => {
    const n = parseFloat(amount);
    if (!n || n <= 0) return;
    setLoading(true);
    try {
      await api.withdraw(n);
      setAmount("");
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-zinc-900/50 border-zinc-800 md:col-span-2">
          <CardContent className="p-6">
            <div className="text-xs text-zinc-500 uppercase tracking-wider">Paper Balance</div>
            <div className="text-4xl font-semibold text-white mt-2 tracking-tight">
              {formatCurrency(wallet?.balance || 0)}
            </div>
            <div className="flex items-center gap-4 mt-4 text-sm">
              <div>
                <span className="text-zinc-500">Deposited:</span>{" "}
                <span className="text-emerald-400">{formatCurrency(wallet?.total_deposited || 0)}</span>
              </div>
              <div>
                <span className="text-zinc-500">Withdrawn:</span>{" "}
                <span className="text-red-400">{formatCurrency(wallet?.total_withdrawn || 0)}</span>
              </div>
              <div>
                <span className="text-zinc-500">Trade P&L:</span>{" "}
                <span className={wallet && wallet.total_pnl >= 0 ? "text-emerald-400" : "text-red-400"}>
                  {formatCurrency(wallet?.total_pnl || 0)}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/50 border-zinc-800 md:col-span-2">
          <CardContent className="p-6 space-y-4">
            <div className="text-xs text-zinc-500 uppercase tracking-wider">Manage Funds</div>
            <div className="flex gap-2">
              <input
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="Amount (USD)"
                className="flex-1 px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
              />
              <Button
                onClick={handleDeposit}
                disabled={loading || !amount}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <ArrowUpRight className="w-4 h-4 mr-1" />
                Deposit
              </Button>
              <Button
                onClick={handleWithdraw}
                disabled={loading || !amount}
                variant="outline"
                className="border-red-500/30 text-red-400 hover:bg-red-500/10"
              >
                <ArrowDownRight className="w-4 h-4 mr-1" />
                Withdraw
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>

      <WalletTransactions />
    </div>
  );
}

function WalletTransactions() {
  const [txs, setTxs] = useState<import("@/lib/api").WalletTransaction[]>([]);

  const fetchTxs = useCallback(() => {
    api.walletTransactions(50).then(setTxs).catch(console.error);
  }, []);

  useEffect(() => {
    fetchTxs();
    const interval = setInterval(fetchTxs, 5000);
    return () => clearInterval(interval);
  }, [fetchTxs]);

  return (
    <Card className="bg-zinc-900/50 border-zinc-800">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium text-zinc-300">Transaction History</CardTitle>
      </CardHeader>
      <CardContent>
        {txs.length === 0 ? (
          <div className="text-sm text-zinc-500 py-8 text-center">No transactions</div>
        ) : (
          <div className="space-y-2">
            {txs.map((tx) => (
              <div key={tx.id} className="flex items-center justify-between p-3 rounded-lg bg-zinc-800/50">
                <div className="flex items-center gap-3">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      tx.transaction_type === "DEPOSIT"
                        ? "bg-emerald-500"
                        : tx.transaction_type === "WITHDRAW"
                        ? "bg-red-500"
                        : tx.transaction_type === "TRADE_PNL"
                        ? tx.amount >= 0
                          ? "bg-emerald-500"
                          : "bg-red-500"
                        : "bg-zinc-500"
                    }`}
                  />
                  <div>
                    <div className="text-sm font-medium text-zinc-200">{tx.transaction_type}</div>
                    <div className="text-xs text-zinc-500">{tx.description || "—"}</div>
                  </div>
                </div>
                <div className="text-right">
                  <div
                    className={`text-sm font-mono font-medium ${
                      tx.amount >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {tx.amount >= 0 ? "+" : ""}
                    {formatCurrency(tx.amount)}
                  </div>
                  <div className="text-xs text-zinc-600">{timeAgo(tx.created_at)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// --- Logs Tab ---

function LogsTab() {
  const [logs, setLogs] = useState<import("@/lib/api").SystemLog[]>([]);
  const [level, setLevel] = useState("");
  const [source, setSource] = useState("");

  const fetchLogs = useCallback(() => {
    api.logs(level || undefined, source || undefined, 200).then(setLogs).catch(console.error);
  }, [level, source]);

  useEffect(() => {
    fetchLogs();
    const interval = setInterval(fetchLogs, 5000);
    return () => clearInterval(interval);
  }, [fetchLogs]);

  const levelColors: Record<string, string> = {
    INFO: "text-blue-400",
    WARNING: "text-amber-400",
    ERROR: "text-red-400",
    CRITICAL: "text-red-500",
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value)}
          className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-200"
        >
          <option value="">All Levels</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="px-3 py-2 rounded-lg bg-zinc-800 border border-zinc-700 text-sm text-zinc-200"
        >
          <option value="">All Sources</option>
          <option value="ORCHESTRATOR">Orchestrator</option>
          <option value="AGENT">Agent</option>
          <option value="EXECUTION">Execution</option>
          <option value="SAFETY">Safety</option>
          <option value="DASHBOARD">Dashboard</option>
        </select>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-0">
          <div className="divide-y divide-zinc-800">
            {logs.map((log) => (
              <div key={log.id} className="p-3 flex items-start gap-3 hover:bg-zinc-800/30 transition-colors">
                <span className={`text-xs font-mono font-medium w-16 shrink-0 ${levelColors[log.level] || "text-zinc-400"}`}>
                  {log.level}
                </span>
                <span className="text-xs font-mono text-zinc-500 w-24 shrink-0">{log.source}</span>
                <span className="text-sm text-zinc-300 flex-1">{log.message}</span>
                <span className="text-xs text-zinc-600 shrink-0">{timeAgo(log.created_at)}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
