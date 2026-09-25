'use client';

import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import {
  Activity,
  AreaChart,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  CalendarDays,
  ChartCandlestick,
  ChevronDown,
  Clock3,
  Command,
  FileClock,
  Gauge,
  LayoutDashboard,
  ListOrdered,
  Menu,
  PlugZap,
  Power,
  Radar,
  Search,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  UserRound,
  WalletCards,
  X,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

declare global {
  interface Document {
    modelContext?: {
      registerTool(
        tool: {
          name: string;
          title: string;
          description: string;
          inputSchema: object;
          annotations: { readOnlyHint: boolean; untrustedContentHint: boolean };
          execute(input: unknown): unknown;
        },
        options: { signal: AbortSignal },
      ): void | Promise<void>;
    };
  }
}

const nav = [
  [LayoutDashboard, 'Dashboard'],
  [Radar, 'Scanner'],
  [ChartCandlestick, 'Watchlist'],
  [WalletCards, 'Positions'],
  [ListOrdered, 'Orders'],
  [FileClock, 'Trades'],
  [BarChart3, 'Analytics'],
  [Bot, 'Agent'],
  [Command, 'Logs'],
  [Settings, 'Settings'],
] as const;

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';

type Account = {
  configured?: boolean;
  cash: number;
  equity: number;
  buying_power: number;
  unrealized_pnl: number;
  currency: string;
};

type Position = {
  symbol: string;
  direction: string;
  quantity: number;
  entry: number;
  stop_loss?: number;
  take_profit?: number;
  strategy?: string;
};

type Order = {
  id: string;
  symbol: string;
  status: string;
  quantity: number;
  fill_price?: number;
  created_at?: string;
};

type Trade = {
  symbol: string;
  direction: string;
  quantity: number;
  entry: number;
  exit: number;
  pnl: number;
  closed_at?: string;
  exit_reason?: string;
};

type AgentState = {
  state: 'STOPPED' | 'RUNNING' | 'PAUSED';
  operation?: string | null;
  kill_switch: boolean;
  last_scan?: string | null;
  counters: {
    symbols_scanned: number;
    signals_found: number;
    rejected: number;
    approved: number;
  };
};

type BrokerInfo = {
  provider: string;
  environment: string;
  orderSubmissionEnabled: boolean;
  connected: boolean;
};

type ScannerRow = {
  symbol: string;
  price: number;
  change_percent: number;
  relative_volume: number;
  rsi: number;
  trend: string;
  shortable: boolean;
};

type EventItem = {
  timestamp: string;
  category: string;
  message: string;
  context?: Record<string, unknown>;
};

type Analytics = {
  total_trades: number;
  win_rate: number;
  average_win: number;
  average_loss: number;
  profit_factor: number;
  expectancy: number;
};

type AppData = {
  account: Account | null;
  positions: Position[];
  orders: Order[];
  trades: Trade[];
  analytics: Analytics | null;
  agent: AgentState;
  notifications: EventItem[];
  todayPnl: number;
};

const initialAgent: AgentState = {
  state: 'STOPPED',
  operation: null,
  kill_switch: false,
  last_scan: null,
  counters: { symbols_scanned: 0, signals_found: 0, rejected: 0, approved: 0 },
};

const initialData: AppData = {
  account: null,
  positions: [],
  orders: [],
  trades: [],
  analytics: null,
  agent: initialAgent,
  notifications: [],
  todayPnl: 0,
};

function money(value: number | undefined, currency = 'CZK') {
  if (value === undefined || !Number.isFinite(value)) return '—';
  return `${new Intl.NumberFormat('cs-CZ', { maximumFractionDigits: 2 }).format(value)} ${currency}`;
}

function numberValue(value: unknown) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

async function login(password: string) {
  const response = await fetch(`${apiBase}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@deetrader.local', password }),
  });
  if (!response.ok) throw new Error('Neplatné administrátorské heslo.');
  const payload = (await response.json()) as { access_token?: string };
  if (!payload.access_token) throw new Error('Server nevrátil přístupový token.');
  return payload.access_token;
}

function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <span><ShieldCheck size={21} /></span>
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  );
}

function TrendIndicator({ trend }: { trend: string }) {
  const rising = trend.toLowerCase() === 'up';
  return <span className={`trend-indicator ${rising ? 'trend-up' : 'trend-down'}`} title="Směr trendu není sám o sobě pokyn k nákupu nebo prodeji">
    {rising ? <ArrowUpRight size={14} aria-hidden="true" /> : <ArrowDownRight size={14} aria-hidden="true" />}
    <span>{rising ? 'Růst' : 'Pokles'}</span>
  </span>;
}

type EquityRange = '1D' | '1W' | '1M' | '3M' | 'YTD' | 'ALL';

const equityRanges: EquityRange[] = ['1D', '1W', '1M', '3M', 'YTD', 'ALL'];

function EquityChart({ account, trades, currency, currentTime }: { account: Account; trades: Trade[]; currency: string; currentTime: number }) {
  const [range, setRange] = useState<EquityRange>('1M');
  const now = currentTime;
  const datedTrades = trades
    .filter((trade) => trade.closed_at && Number.isFinite(new Date(trade.closed_at).getTime()))
    .map((trade) => ({ time: new Date(trade.closed_at as string).getTime(), pnl: numberValue(trade.pnl) }))
    .sort((a, b) => a.time - b.time);
  const cutoff = range === '1D' ? now - 86_400_000
    : range === '1W' ? now - 7 * 86_400_000
      : range === '1M' ? now - 30 * 86_400_000
        : range === '3M' ? now - 90 * 86_400_000
          : range === 'YTD' ? new Date(new Date(now).getFullYear(), 0, 1).getTime()
            : datedTrades[0]?.time ?? now;
  const totalClosedPnl = datedTrades.reduce((sum, trade) => sum + trade.pnl, 0);
  const startingEquity = numberValue(account.equity) - totalClosedPnl;
  let equityAtCutoff = startingEquity;
  for (const trade of datedTrades) if (trade.time < cutoff) equityAtCutoff += trade.pnl;
  const visibleTrades = datedTrades.filter((trade) => trade.time >= cutoff);
  const points = [{ time: cutoff, value: equityAtCutoff }];
  let runningEquity = equityAtCutoff;
  for (const trade of visibleTrades) {
    runningEquity += trade.pnl;
    points.push({ time: trade.time, value: runningEquity });
  }
  points.push({ time: now, value: numberValue(account.equity) });
  const hasHistory = visibleTrades.length > 0;
  const values = points.map((point) => point.value);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const valueSpan = maxValue - minValue || Math.max(Math.abs(maxValue) * 0.02, 1);
  const timeSpan = Math.max(now - cutoff, 1);
  const coordinates = points.map((point) => {
    const x = ((point.time - cutoff) / timeSpan) * 900;
    const y = 220 - ((point.value - minValue) / valueSpan) * 180;
    return `${Math.max(0, Math.min(900, x)).toFixed(1)},${Math.max(30, Math.min(220, y)).toFixed(1)}`;
  }).join(' ');
  const dateFormatter = new Intl.DateTimeFormat('cs-CZ', { day: '2-digit', month: 'short' });

  return <Card className={`chart-card ${hasHistory ? '' : 'empty-chart'}`}>
    <div className="card-title">
      <div><span>Equity curve</span><strong>{money(account.equity, currency)}</strong></div>
      <div className="range-tabs" aria-label="Období equity grafu">
        {equityRanges.map((value) => <button key={value} type="button" className={range === value ? 'selected' : ''} aria-pressed={range === value} onClick={() => setRange(value)}>{value}</button>)}
      </div>
    </div>
    {hasHistory ? <>
      <div className="chart-wrap"><svg viewBox="0 0 900 250" className="mini-chart" preserveAspectRatio="none" aria-label={`Equity za období ${range}`}><defs><linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#2dd4bf" stopOpacity=".25"/><stop offset="1" stopColor="#2dd4bf" stopOpacity="0"/></linearGradient></defs>{[40,85,130,175,220].map((y) => <line key={y} x1="0" y1={y} x2="900" y2={y} stroke="#26303b"/>)}<polyline points={`0,250 ${coordinates} 900,250`} fill="url(#equity-fill)" stroke="none"/><polyline points={coordinates} fill="none" stroke="#2dd4bf" strokeWidth="2.5" vectorEffect="non-scaling-stroke"/><circle cx={coordinates.split(' ').at(-1)?.split(',')[0]} cy={coordinates.split(' ').at(-1)?.split(',')[1]} r="4" fill="#2dd4bf"/></svg></div>
      <div className="chart-axis"><span>{dateFormatter.format(cutoff)}</span><span>{dateFormatter.format(cutoff + timeSpan / 2)}</span><span>{dateFormatter.format(now)}</span></div>
    </> : <EmptyState title={`Bez změn za období ${range}`} description="Pro zvolené období nejsou žádné uzavřené obchody. Graf se vykresluje pouze ze skutečné historie účtu." />}
  </Card>;
}

function SearchDialog({
  open,
  onOpenChange,
  onNavigate,
  scannerRows,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  onNavigate: (value: string) => void;
  scannerRows: ScannerRow[];
}) {
  const [query, setQuery] = useState('');
  const normalized = query.trim().toLowerCase();
  const sections = nav.filter(([, label]) => label.toLowerCase().includes(normalized));
  const instruments = scannerRows.filter((row) => row.symbol.toLowerCase().includes(normalized));
  return (
    <Dialog open={open} onOpenChange={(value) => { onOpenChange(value); if (!value) setQuery(''); }}>
      <DialogContent className="search-dialog">
        <DialogHeader>
          <DialogTitle>Vyhledávání</DialogTitle>
          <DialogDescription>Najděte sekci nebo ticker z posledního scanu.</DialogDescription>
        </DialogHeader>
        <div className="search-field"><Search size={16} /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Např. Scanner nebo AAPL" /></div>
        <div className="search-results">
          {sections.map(([Icon, label]) => (
            <button key={label} onClick={() => { onNavigate(label); onOpenChange(false); }}>
              <Icon size={16} /><span>{label}</span><small>Sekce</small>
            </button>
          ))}
          {instruments.map((row) => (
            <button key={row.symbol} onClick={() => { onNavigate('Scanner'); onOpenChange(false); }}>
              <ChartCandlestick size={16} /><span>{row.symbol}</span><small>{row.price.toFixed(2)}</small>
            </button>
          ))}
          {!sections.length && !instruments.length && <EmptyState title="Nic nenalezeno" description="Ticker se zobrazí až po dokončení scanu." />}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ScannerConfigDialog({
  open,
  onOpenChange,
  config,
  onSave,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  config: ScannerConfig;
  onSave: (config: ScannerConfig) => void;
}) {
  const [draft, setDraft] = useState(config);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="trade-dialog">
        <DialogHeader>
          <DialogTitle>Nastavení scanneru</DialogTitle>
          <DialogDescription>Filtry se použijí při příštím spuštění. Výsledky nejsou investiční doporučení.</DialogDescription>
        </DialogHeader>
        <div className="config-grid">
          <label htmlFor="scanner-symbols">Tickery<Input id="scanner-symbols" value={draft.symbols} onChange={(event) => setDraft({ ...draft, symbols: event.target.value.toUpperCase() })} /></label>
          <label htmlFor="scanner-min-price">Minimální cena<Input id="scanner-min-price" type="number" value={draft.minPrice} onChange={(event) => setDraft({ ...draft, minPrice: event.target.value })} /></label>
          <label htmlFor="scanner-max-price">Maximální cena<Input id="scanner-max-price" type="number" value={draft.maxPrice} onChange={(event) => setDraft({ ...draft, maxPrice: event.target.value })} /></label>
          <label htmlFor="scanner-rel-volume">Min. relativní objem<Input id="scanner-rel-volume" type="number" step="0.1" value={draft.minRelativeVolume} onChange={(event) => setDraft({ ...draft, minRelativeVolume: event.target.value })} /></label>
          <label htmlFor="scanner-shortable" className="check-row"><input id="scanner-shortable" type="checkbox" checked={draft.shortable} onChange={(event) => setDraft({ ...draft, shortable: event.target.checked })} /> Pouze shortovatelné</label>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Zrušit</Button><Button onClick={() => { onSave(draft); onOpenChange(false); }}>Použít filtry</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PaperAccountDialog({ open, onOpenChange, onConfigured }: { open: boolean; onOpenChange: (value: boolean) => void; onConfigured: () => void }) {
  const [amount, setAmount] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setStatus('');
    try {
      const token = await login(password);
      const response = await fetch(`${apiBase}/api/v1/paper/account`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ starting_cash: Number(amount) }),
      });
      const payload = (await response.json()) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || 'Nastavení účtu se nezdařilo.');
      setPassword(''); setAmount(''); onConfigured(); onOpenChange(false);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : 'Nastavení účtu se nezdařilo.');
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="trade-dialog">
        <DialogHeader><DialogTitle>Nastavit PAPER účet</DialogTitle><DialogDescription>Zadejte vlastní testovací kapitál. Nevytvoří se žádné pozice ani ukázkové obchody.</DialogDescription></DialogHeader>
        <div className="config-grid">
          <label htmlFor="paper-capital">Počáteční kapitál v CZK<Input id="paper-capital" type="number" min="1" value={amount} onChange={(event) => setAmount(event.target.value)} /></label>
          <label htmlFor="paper-password">Heslo správce DeeTrader<Input id="paper-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        </div>
        {status && <div className="form-error">{status}</div>}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Zrušit</Button><Button disabled={busy || Number(amount) <= 0 || !password} onClick={() => void submit()}>{busy ? 'Nastavuji…' : 'Nastavit účet'}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type AgentAction = 'start' | 'stop' | 'emergency-stop';

function AgentActionDialog({ open, action, onOpenChange, onDone }: { open: boolean; action: AgentAction; onOpenChange: (value: boolean) => void; onDone: () => void }) {
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const emergency = action === 'emergency-stop';
  const submit = async () => {
    setBusy(true); setStatus('');
    try {
      const token = await login(password);
      const url = emergency ? `${apiBase}/api/v1/agent/emergency-stop` : `${apiBase}/api/v1/agent/${action}`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(emergency ? { cancel_pending: true, close_positions: false } : {}),
      });
      const payload = (await response.json()) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || 'Akci se nepodařilo provést.');
      setPassword(''); onDone(); onOpenChange(false);
    } catch (error) { setStatus(error instanceof Error ? error.message : 'Akci se nepodařilo provést.'); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="trade-dialog">
        <DialogHeader>
          <DialogTitle>{emergency ? 'Aktivovat nouzové zastavení?' : action === 'start' ? 'Spustit agenta?' : 'Zastavit agenta?'}</DialogTitle>
          <DialogDescription>{emergency ? 'Agent se zastaví a čekající pokyny se zruší. Otevřené pozice zůstanou beze změny.' : 'Akce změní skutečný stav backendového agenta.'}</DialogDescription>
        </DialogHeader>
        <div className="config-grid"><label htmlFor="agent-password">Heslo správce DeeTrader<Input id="agent-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label></div>
        {status && <div className="form-error">{status}</div>}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Zrušit</Button><Button variant={emergency ? 'destructive' : 'default'} disabled={busy || !password} onClick={() => void submit()}>{busy ? 'Provádím…' : emergency ? 'Nouzově zastavit' : 'Potvrdit'}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function BrokerConnectionDialog({ open, onOpenChange, onConnected }: { open: boolean; onOpenChange: (value: boolean) => void; onConnected: () => void }) {
  const [baseUrl, setBaseUrl] = useState('https://127.0.0.1:5000/v1/api');
  const [accountId, setAccountId] = useState('');
  const [password, setPassword] = useState('');
  const [status, setStatus] = useState('');
  const connect = async () => {
    setStatus('Připojuji…');
    try {
      const token = await login(password);
      const response = await fetch(`${apiBase}/api/v1/broker/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ method: 'gateway', base_url: baseUrl, account_id: accountId || null, verify_tls: false, environment: 'paper', order_submission_enabled: false }),
      });
      const payload = (await response.json()) as { detail?: string };
      if (!response.ok) throw new Error(payload.detail || 'IBKR připojení se nezdařilo.');
      setPassword(''); setStatus('IBKR PAPER účet je připojen.'); onConnected();
    } catch (error) { setStatus(error instanceof Error ? error.message : 'IBKR připojení se nezdařilo.'); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="broker-dialog">
        <DialogHeader><DialogTitle>Připojit Interactive Brokers</DialogTitle><DialogDescription>Bezpečné připojení k PAPER relaci Client Portal Gateway.</DialogDescription></DialogHeader>
        <div className="config-grid"><label htmlFor="broker-url">IBKR API URL<Input id="broker-url" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label><label htmlFor="broker-account">Account ID<Input id="broker-account" value={accountId} onChange={(event) => setAccountId(event.target.value)} /></label><label htmlFor="broker-password">Heslo správce DeeTrader<Input id="broker-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} /></label></div>
        {status && <div className="connection-status">{status}</div>}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Zavřít</Button><Button disabled={!baseUrl || !password} onClick={() => void connect()}>Otestovat a připojit</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type ScannerConfig = { symbols: string; minPrice: string; maxPrice: string; minRelativeVolume: string; shortable: boolean };

const defaultScannerSymbols = 'AAPL, MSFT, NVDA, AMD, AMZN, GOOGL, META, TSLA, AVGO, NFLX, PLTR, INTC, CSCO, ORCL, CRM, ADBE, QCOM, MU, ARM, SMCI, JPM, BAC, V, MA, WMT, COST, KO, DIS, NKE, UBER';

function DataTable({ title, subtitle, headers, rows }: { title: string; subtitle: string; headers: string[]; rows: ReactNode[][] }) {
  return (
    <Card className="table-card secondary-card">
      <div className="card-title"><div><span>{title}</span><small>{subtitle}</small></div></div>
      {rows.length ? <Table><TableHeader><TableRow>{headers.map((header) => <TableHead key={header}>{header}</TableHead>)}</TableRow></TableHeader><TableBody>{rows.map((row, index) => <TableRow key={index}>{row.map((cell, cellIndex) => <TableCell key={cellIndex}>{cell}</TableCell>)}</TableRow>)}</TableBody></Table> : <EmptyState title={`Žádné ${title.toLowerCase()}`} description="Tato tabulka se naplní pouze skutečnými daty z PAPER účtu." />}
    </Card>
  );
}

export function TradingTerminal() {
  const [active, setActive] = useState('Dashboard');
  const [mobile, setMobile] = useState(false);
  const [now, setNow] = useState<Date | null>(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [data, setData] = useState<AppData>(initialData);
  const [broker, setBroker] = useState<BrokerInfo>({ provider: 'paper', environment: 'paper', orderSubmissionEnabled: false, connected: false });
  const [scannerRows, setScannerRows] = useState<ScannerRow[]>([]);
  const [scannerRunning, setScannerRunning] = useState(false);
  const [scannerMessage, setScannerMessage] = useState('Scanner zatím nebyl spuštěn.');
  const [scannerConfig, setScannerConfig] = useState<ScannerConfig>({ symbols: defaultScannerSymbols, minPrice: '50', maxPrice: '350', minRelativeVolume: '1.5', shortable: true });
  const [searchOpen, setSearchOpen] = useState(false);
  const [scannerConfigOpen, setScannerConfigOpen] = useState(false);
  const [paperOpen, setPaperOpen] = useState(false);
  const [brokerOpen, setBrokerOpen] = useState(false);
  const [agentDialogOpen, setAgentDialogOpen] = useState(false);
  const [agentAction, setAgentAction] = useState<AgentAction>('start');

  const refresh = useCallback(async () => {
    try {
      const [dashboardResponse, ordersResponse, tradesResponse, analyticsResponse, notificationsResponse, brokerResponse] = await Promise.all([
        fetch(`${apiBase}/api/v1/dashboard`),
        fetch(`${apiBase}/api/v1/orders`),
        fetch(`${apiBase}/api/v1/trades?environment=paper`),
        fetch(`${apiBase}/api/v1/analytics`),
        fetch(`${apiBase}/api/v1/notifications`),
        fetch(`${apiBase}/api/v1/broker`),
      ]);
      if (!dashboardResponse.ok) throw new Error('Backend unavailable');
      const dashboard = await dashboardResponse.json() as { account: Account; positions: Position[]; today_pnl: number; agent: AgentState };
      const brokerPayload = await brokerResponse.json() as Record<string, unknown>;
      setData({
        account: dashboard.account,
        positions: dashboard.positions || [],
        orders: ordersResponse.ok ? await ordersResponse.json() as Order[] : [],
        trades: tradesResponse.ok ? await tradesResponse.json() as Trade[] : [],
        analytics: analyticsResponse.ok ? await analyticsResponse.json() as Analytics : null,
        notifications: notificationsResponse.ok ? await notificationsResponse.json() as EventItem[] : [],
        agent: dashboard.agent || initialAgent,
        todayPnl: numberValue(dashboard.today_pnl),
      });
      setBroker({ provider: typeof brokerPayload.provider === 'string' ? brokerPayload.provider : 'paper', environment: typeof brokerPayload.environment === 'string' ? brokerPayload.environment : 'paper', orderSubmissionEnabled: Boolean(brokerPayload.order_submission_enabled), connected: brokerPayload.connection_state === 'CONNECTED' });
      setBackendOnline(true);
    } catch {
      setBackendOnline(false);
    }
  }, []);

  useEffect(() => { const initial = window.setTimeout(() => void refresh(), 0); const timer = window.setInterval(() => void refresh(), 15000); return () => { window.clearTimeout(initial); window.clearInterval(timer); }; }, [refresh]);
  useEffect(() => { const update = () => setNow(new Date()); update(); const timer = setInterval(update, 1000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    const context = document.modelContext;
    if (!context?.registerTool) return;
    const lifecycle = new AbortController();
    const registration = context.registerTool({ name: 'open_deetrader_section', title: 'Open DeeTrader section', description: 'Open a visible DeeTrader section without placing orders.', inputSchema: { type: 'object', properties: { section: { type: 'string' } }, required: ['section'] }, annotations: { readOnlyHint: true, untrustedContentHint: false }, execute(input) { if (typeof input === 'object' && input && 'section' in input) setActive(String((input as { section: unknown }).section)); return { ok: true }; } }, { signal: lifecycle.signal });
    void Promise.resolve(registration).catch(() => undefined);
    return () => lifecycle.abort();
  }, []);

  const accountConfigured = broker.provider === 'ibkr' || Boolean(data.account?.configured);
  const currency = data.account?.currency || 'CZK';
  const exposure = data.positions.reduce((sum, position) => sum + numberValue(position.quantity) * numberValue(position.entry), 0);
  const riskPercent = data.account?.equity ? exposure / data.account.equity * 100 : 0;
  const tradingMode = broker.environment === 'live' ? 'LIVE' : 'PAPER';

  const runScanner = async () => {
    setScannerRunning(true); setScannerMessage('Probíhá scan…');
    try {
      const symbols = scannerConfig.symbols.split(',').map((symbol) => symbol.trim().toUpperCase()).filter(Boolean);
      const response = await fetch(`${apiBase}/api/v1/scanner`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ symbols, filters: { min_price: Number(scannerConfig.minPrice), max_price: Number(scannerConfig.maxPrice), min_relative_volume: Number(scannerConfig.minRelativeVolume), shortable: scannerConfig.shortable } }) });
      if (!response.ok) throw new Error('Scanner se nepodařilo spustit.');
      const rows = await response.json() as ScannerRow[];
      setScannerRows(rows); setScannerMessage(rows.length ? `Nalezeno ${rows.length} kandidátů v simulovaných datech.` : 'Žádný instrument nesplnil nastavené filtry.');
      await refresh();
    } catch (error) { setScannerRows([]); setScannerMessage(error instanceof Error ? error.message : 'Scanner se nepodařilo spustit.'); }
    finally { setScannerRunning(false); }
  };

  const openAgentAction = (action: AgentAction) => { setAgentAction(action); setAgentDialogOpen(true); };
  const configureAction = () => { if (active === 'Scanner') setScannerConfigOpen(true); else if (!accountConfigured) setPaperOpen(true); else setActive('Settings'); };

  const renderDashboard = () => {
    if (!accountConfigured) return <Card className="setup-card"><div className="setup-icon"><WalletCards size={24} /></div><div><Badge className="paper-badge">PAPER</Badge><h2>Nejdřív nastavte testovací účet</h2><p>DeeTrader nezačne s vymyšleným zůstatkem ani historií. Zadejte vlastní testovací kapitál; pozice, obchody a statistiky zůstanou prázdné, dokud je skutečně nevytvoříte.</p></div><Button onClick={() => setPaperOpen(true)}>Nastavit PAPER účet</Button></Card>;
    const metrics = [
      ['Account equity', money(data.account?.equity, currency), 'Aktuální stav'],
      ['Buying power', money(data.account?.buying_power, currency), 'Podle brokera'],
      ['Today P&L', money(data.todayPnl, currency), data.trades.length ? 'Uzavřené obchody' : 'Bez obchodů'],
      ['Current exposure', money(exposure, currency), `${data.positions.length} pozic`],
    ];
    return <>
      <div className="metric-grid">{metrics.map(([label, value, note]) => <Card className="metric-card" key={label}><div><span>{label}</span><Gauge size={16} /></div><strong>{value}</strong><small>{note}</small></Card>)}</div>
      <div className="chart-grid">{data.account ? <EquityChart account={data.account} trades={data.trades} currency={currency} currentTime={now?.getTime() ?? 0} /> : <Card className="chart-card empty-chart"><EmptyState title="Účetní data nejsou dostupná" description="Graf se zobrazí po načtení účtu od brokera." /></Card>}<Card className="risk-card"><div className="card-title"><span>Exposure</span><Badge variant="outline">{data.positions.length ? 'ACTIVE' : 'NONE'}</Badge></div><div className="risk-ring" style={{ background: `conic-gradient(#2dd4bf 0 ${Math.min(riskPercent, 100) * 3.6}deg,#202a33 ${Math.min(riskPercent, 100) * 3.6}deg)` }}><div><strong>{riskPercent.toFixed(2)}%</strong><span>of equity</span></div></div><dl><div><dt>Open exposure</dt><dd>{money(exposure, currency)}</dd></div><div><dt>Positions</dt><dd>{data.positions.length}</dd></div></dl></Card></div>
      <DataTable title="Open positions" subtitle="Skutečný stav PAPER portfolia" headers={['Ticker', 'Direction', 'Qty', 'Entry', 'Stop', 'Target', 'Strategy']} rows={data.positions.map((position) => [<b key="s">{position.symbol}</b>, position.direction, numberValue(position.quantity).toFixed(4), numberValue(position.entry).toFixed(2), position.stop_loss ? numberValue(position.stop_loss).toFixed(2) : '—', position.take_profit ? numberValue(position.take_profit).toFixed(2) : '—', position.strategy || '—'])} />
      <div className="bottom-grid"><Card className="table-card"><div className="card-title"><div><span>Scanner candidates</span><small>Pouze poslední skutečně spuštěný scan</small></div><Badge variant="outline">{scannerRows.length}</Badge></div>{scannerRows.length ? <Table><TableHeader><TableRow>{['Ticker', 'Price', 'Change', 'Rel. vol', 'RSI', 'Trend'].map((header) => <TableHead key={header}>{header}</TableHead>)}</TableRow></TableHeader><TableBody>{scannerRows.map((row) => <TableRow key={row.symbol}><TableCell><b>{row.symbol}</b></TableCell><TableCell>{row.price.toFixed(2)}</TableCell><TableCell>{row.change_percent.toFixed(2)}%</TableCell><TableCell>{row.relative_volume.toFixed(2)}×</TableCell><TableCell>{row.rsi}</TableCell><TableCell><TrendIndicator trend={row.trend} /></TableCell></TableRow>)}</TableBody></Table> : <EmptyState title="Scanner nebyl spuštěn" description="Výsledky se zobrazí až po kliknutí na Run scan." action={<Button size="sm" onClick={() => { setActive('Scanner'); void runScanner(); }}>Run scan</Button>} />}</Card><EventList events={data.notifications} /></div>
    </>;
  };

  const renderSecondary = () => {
    if (active === 'Scanner') return <Card className="table-card secondary-card"><div className="card-title"><div><span>Market scanner</span><small>Simulovaná tržní data · kandidáti pro další analýzu</small></div><Button size="sm" disabled={scannerRunning} onClick={() => void runScanner()}>{scannerRunning ? 'Scanning…' : 'Run scan'}</Button></div><div className="scanner-message">{scannerMessage}</div>{scannerRows.length ? <Table><TableHeader><TableRow>{['Ticker', 'Price', 'Change', 'Rel. volume', 'RSI', 'Trend', 'Shortable'].map((header) => <TableHead key={header}>{header}</TableHead>)}</TableRow></TableHeader><TableBody>{scannerRows.map((row) => <TableRow key={row.symbol}><TableCell><b>{row.symbol}</b></TableCell><TableCell>{row.price.toFixed(2)}</TableCell><TableCell>{row.change_percent.toFixed(2)}%</TableCell><TableCell>{row.relative_volume.toFixed(2)}×</TableCell><TableCell>{row.rsi}</TableCell><TableCell><TrendIndicator trend={row.trend} /></TableCell><TableCell>{row.shortable ? 'Ano' : 'Ne'}</TableCell></TableRow>)}</TableBody></Table> : <EmptyState title="Žádné výsledky" description="Spusťte scanner; tabulka se neplní ukázkovými hodnotami." />}</Card>;
    if (active === 'Positions') return <DataTable title="Positions" subtitle="Stav PAPER účtu" headers={['Ticker', 'Direction', 'Quantity', 'Entry', 'Stop loss', 'Take profit', 'Strategy']} rows={data.positions.map((position) => [<b key="s">{position.symbol}</b>, position.direction, numberValue(position.quantity).toFixed(4), numberValue(position.entry).toFixed(2), position.stop_loss ? numberValue(position.stop_loss).toFixed(2) : '—', position.take_profit ? numberValue(position.take_profit).toFixed(2) : '—', position.strategy || '—'])} />;
    if (active === 'Orders') return <DataTable title="Orders" subtitle="Pokyny vytvořené v PAPER účtu" headers={['Order ID', 'Ticker', 'Quantity', 'Fill price', 'Status', 'Created']} rows={data.orders.map((order) => [<b key="id">{order.id.slice(0, 8)}</b>, order.symbol, numberValue(order.quantity).toFixed(4), order.fill_price ? numberValue(order.fill_price).toFixed(2) : '—', order.status, order.created_at ? new Date(order.created_at).toLocaleString('cs-CZ') : '—'])} />;
    if (active === 'Trades') return <DataTable title="Trades" subtitle="Pouze skutečně uzavřené PAPER obchody" headers={['Date', 'Ticker', 'Direction', 'Quantity', 'Entry', 'Exit', 'P&L', 'Exit reason']} rows={data.trades.map((trade) => [trade.closed_at ? new Date(trade.closed_at).toLocaleString('cs-CZ') : '—', <b key="s">{trade.symbol}</b>, trade.direction, numberValue(trade.quantity).toFixed(4), numberValue(trade.entry).toFixed(2), numberValue(trade.exit).toFixed(2), money(numberValue(trade.pnl), currency), trade.exit_reason || '—'])} />;
    if (active === 'Watchlist') return <Card className="secondary-card"><EmptyState title="Watchlist je prázdný" description="Nebudeme předstírat sledované instrumenty. Přidávání bude dostupné z výsledků scanneru." /></Card>;
    if (active === 'Analytics') return data.analytics?.total_trades ? <div className="metric-grid">{[['Total trades', data.analytics.total_trades], ['Win rate', `${data.analytics.win_rate.toFixed(1)}%`], ['Profit factor', data.analytics.profit_factor.toFixed(2)], ['Expectancy', money(data.analytics.expectancy, currency)]].map(([label, value]) => <Card className="metric-card" key={label}><div><span>{label}</span></div><strong>{value}</strong></Card>)}</div> : <Card className="secondary-card"><EmptyState title="Analytics zatím nemá data" description="Statistiky se vypočítají až ze skutečně uzavřených PAPER obchodů." /></Card>;
    if (active === 'Agent' || active === 'Logs') return <div className="agent-grid"><Card className="activity-card"><div className="card-title"><div><span>Trading agent</span><small>Skutečný backendový stav</small></div><Badge variant="outline">{data.agent.state}</Badge></div>{[['Current operation', data.agent.operation || 'Žádná'], ['Last scan', data.agent.last_scan ? new Date(data.agent.last_scan).toLocaleString('cs-CZ') : 'Nikdy'], ['Symbols scanned', data.agent.counters.symbols_scanned], ['Signals found', data.agent.counters.signals_found], ['Kill switch', data.agent.kill_switch ? 'AKTIVNÍ' : 'Neaktivní']].map(([label, value]) => <div className="settings-row" key={label}><span>{label}</span><b>{value}</b></div>)}<Button variant="destructive" className="kill-button" disabled={data.agent.kill_switch} onClick={() => openAgentAction('emergency-stop')}>{data.agent.kill_switch ? 'Emergency stop aktivní' : 'Emergency stop'}</Button></Card><EventList events={data.notifications} /></div>;
    if (active === 'Settings') return <div className="settings-grid"><Card className="activity-card"><div className="card-title"><div><span>PAPER account</span><small>Vlastní testovací kapitál, žádná ukázková historie</small></div><WalletCards size={17} /></div>{[['Configured', accountConfigured ? 'Ano' : 'Ne'], ['Cash', accountConfigured ? money(data.account?.cash, currency) : 'Nenastaveno'], ['Equity', accountConfigured ? money(data.account?.equity, currency) : 'Nenastaveno'], ['Positions', data.positions.length]].map(([label, value]) => <div className="settings-row" key={label}><span>{label}</span><b>{value}</b></div>)}{!accountConfigured && <Button onClick={() => setPaperOpen(true)}>Nastavit PAPER účet</Button>}</Card><Card className="activity-card broker-settings"><div className="card-title"><div><span>Broker & execution</span><small>Připojení platí pro aktuální běh serveru</small></div><Badge className="paper-badge">{tradingMode}</Badge></div>{[['Broker', broker.provider === 'ibkr' ? 'Interactive Brokers' : 'Paper broker'], ['Connection', broker.connected ? 'Connected' : 'Offline'], ['Live trading', broker.environment === 'live' ? 'Enabled' : 'Disabled'], ['Order submission', broker.provider === 'ibkr' && broker.orderSubmissionEnabled ? 'Enabled' : 'Disabled']].map(([label, value]) => <div className="settings-row" key={label}><span>{label}</span><b>{value}</b></div>)}<Button className="connect-broker-button" onClick={() => setBrokerOpen(true)}><PlugZap size={15} />Připojit Interactive Brokers</Button></Card></div>;
    return null;
  };

  return <div className="terminal-shell">
    <aside className={`sidebar ${mobile ? 'sidebar-open' : ''}`}><div className="brand"><span className="brand-mark"><AreaChart size={19} /></span><span>DeeTrader</span><button className="mobile-close" onClick={() => setMobile(false)} aria-label="Close navigation"><X size={18} /></button></div><nav>{nav.map(([Icon, label]) => <button key={label} onClick={() => { setActive(label); setMobile(false); }} className={active === label ? 'nav-active' : ''}><Icon size={17} /><span>{label}</span>{label === 'Scanner' && scannerRows.length > 0 && <span className="nav-count">{scannerRows.length}</span>}</button>)}</nav><div className="sidebar-foot"><div><span className={`status-dot ${backendOnline ? 'online' : ''}`} /><span>{broker.provider === 'ibkr' ? 'IBKR broker' : 'Paper broker'}</span><b>{backendOnline ? 'Connected' : 'Offline'}</b></div><button className="mode-switch" aria-label="Obchodní režim"><ShieldCheck size={16} /><span>Trading mode</span><Badge className="paper-badge">{tradingMode}</Badge></button><DropdownMenu><DropdownMenuTrigger className="user-row" aria-label="Otevřít nabídku účtu"><span className="avatar">DT</span><span><strong>Trader</strong><small>Administrator</small></span><ChevronDown size={15} /></DropdownMenuTrigger><DropdownMenuContent className="account-menu" side="top" align="start"><DropdownMenuGroup><DropdownMenuLabel><strong>Trader</strong><span>Administrator · {tradingMode}</span></DropdownMenuLabel><DropdownMenuSeparator /><DropdownMenuItem onClick={() => setActive('Settings')}><UserRound />Nastavení účtu</DropdownMenuItem></DropdownMenuGroup></DropdownMenuContent></DropdownMenu></div></aside>
    <main className="main-panel"><header className="topbar"><button className="mobile-menu" onClick={() => setMobile(true)} aria-label="Open navigation"><Menu size={20} /></button><div className="market-state"><span className={`status-dot ${backendOnline ? 'online' : ''}`} /><span>Lokální test</span><small>Tržní stav není připojen</small></div><div className="current-datetime"><span><CalendarDays size={13} />{now ? new Intl.DateTimeFormat('cs-CZ', { dateStyle: 'short', timeZone: 'Europe/Prague' }).format(now) : '—'}</span><b><Clock3 size={13} />{now ? new Intl.DateTimeFormat('cs-CZ', { timeStyle: 'medium', hour12: false, timeZone: 'Europe/Prague' }).format(now) : '—'}</b></div><div className="top-statuses"><span><WalletCards size={14} />Zůstatek <b>{accountConfigured ? money(data.account?.equity, currency) : 'Nenastaveno'}</b></span><span><Activity size={14} />Broker <b className={backendOnline ? 'positive' : 'negative'}>{backendOnline ? 'Online' : 'Offline'}</b></span><span><Bot size={14} />Agent <b>{data.agent.state}</b></span><span>Daily P&L <b>{accountConfigured ? money(data.todayPnl, currency) : '—'}</b></span></div><div className="top-actions"><Button variant="outline" size="icon" aria-label="Search" onClick={() => setSearchOpen(true)}><Search size={16} /></Button><Popover><PopoverTrigger render={<Button variant="outline" size="icon" aria-label="Notifications" />}><Bell size={16} />{data.notifications.length > 0 && <i />}</PopoverTrigger><PopoverContent align="end" className="notification-popover"><PopoverHeader><PopoverTitle>Notifikace</PopoverTitle></PopoverHeader>{data.notifications.length ? data.notifications.slice(0, 6).map((event, index) => <div className="notification-item" key={`${event.timestamp}-${index}`}><span className="status-dot online" /><div><b>{event.message}</b><small>{new Date(event.timestamp).toLocaleString('cs-CZ')} · {event.category}</small></div></div>) : <EmptyState title="Žádné notifikace" description="Události se objeví po skutečné akci v aplikaci." />}</PopoverContent></Popover><button className="paper-badge top-mode">{tradingMode}</button></div></header>
      <section className="content"><div className="page-heading"><div><p>Trading overview</p><h1>{active}</h1></div><div className="heading-actions"><Button className="invest-button" onClick={() => accountConfigured ? setActive('Scanner') : setPaperOpen(true)}><Sparkles size={15} />{accountConfigured ? 'Najít instrument' : 'Nastavit účet'}</Button><Button variant="outline" onClick={configureAction}><SlidersHorizontal size={15} />Configure</Button><Button className="agent-button" onClick={() => openAgentAction(data.agent.state === 'RUNNING' ? 'stop' : 'start')}><Power size={15} />{data.agent.state === 'RUNNING' ? 'Stop agent' : 'Start agent'}</Button></div></div>
      <div className="safety-strip"><ShieldCheck size={16} /><span><b>{accountConfigured ? 'PAPER účet připraven' : 'PAPER účet není nastaven'}</b> — žádné ukázkové zůstatky, pozice ani obchody</span><Badge variant="outline">{data.agent.kill_switch ? 'KILL SWITCH' : '0 violations'}</Badge></div>
      {active === 'Dashboard' ? renderDashboard() : renderSecondary()}
      </section></main>
    <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} onNavigate={setActive} scannerRows={scannerRows} />
    <ScannerConfigDialog open={scannerConfigOpen} onOpenChange={setScannerConfigOpen} config={scannerConfig} onSave={setScannerConfig} />
    <PaperAccountDialog open={paperOpen} onOpenChange={setPaperOpen} onConfigured={() => void refresh()} />
    <AgentActionDialog open={agentDialogOpen} action={agentAction} onOpenChange={setAgentDialogOpen} onDone={() => void refresh()} />
    <BrokerConnectionDialog open={brokerOpen} onOpenChange={setBrokerOpen} onConnected={() => void refresh()} />
  </div>;
}

function EventList({ events }: { events: EventItem[] }) {
  return <Card className="activity-card"><div className="card-title"><span>System activity</span><Badge variant="outline">{events.length}</Badge></div>{events.length ? events.slice(0, 8).map((event, index) => <div className="log-row" key={`${event.timestamp}-${index}`}><span className="status-dot online" /><div><b>{event.message}</b><small>{new Date(event.timestamp).toLocaleString('cs-CZ')} · {event.category}</small></div></div>) : <EmptyState title="Zatím bez událostí" description="Log se naplní po skutečných akcích." />}</Card>;
}
