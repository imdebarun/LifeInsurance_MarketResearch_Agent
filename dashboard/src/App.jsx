import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Shield, TrendingUp, Users, Activity, BarChart3, 
  AlertCircle, Search, ChevronUp, ChevronDown, History 
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, 
  Tooltip as RechartsTooltip, ResponsiveContainer, Cell, Legend
} from 'recharts';

function App() {
  const [data, setData] = useState({ rankings: [], latest: [], history: [] });
  const [loading, setLoading] = useState(true);

  // Dynamic Filters & States
  const [searchTerm, setSearchTerm] = useState('');
  const [sortConfig, setSortConfig] = useState({ key: 'composite_score', direction: 'desc' });
  const [chartMetric, setChartMetric] = useState('score');
  const [selectedHistoryCompany, setSelectedHistoryCompany] = useState('');

  useEffect(() => {
    Promise.all([
      fetch('/rankings_data.json').then(res => res.json()).catch(() => []),
      fetch('/latest_data.json').then(res => res.json()).catch(() => []),
      fetch('/historical_data.json').then(res => res.json()).catch(() => [])
    ]).then(([rankings, latest, history]) => {
      setData({ rankings, latest, history });
      if (rankings.length > 0) {
        setSelectedHistoryCompany(rankings[0].company_name);
      }
      setLoading(false);
    });
  }, []);

  // Compute interactive table data
  const filteredAndSortedTable = useMemo(() => {
    let result = [...data.latest];
    if (searchTerm) {
      result = result.filter(c => c.company_name.toLowerCase().includes(searchTerm.toLowerCase()));
    }
    if (sortConfig.key) {
      result.sort((a, b) => {
        const aVal = a[sortConfig.key] || 0;
        const bVal = b[sortConfig.key] || 0;
        if (aVal < bVal) return sortConfig.direction === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortConfig.direction === 'asc' ? 1 : -1;
        return 0;
      });
    }
    return result;
  }, [data.latest, searchTerm, sortConfig]);

  // Compute Historical Line Chart Data
  const historyChartData = useMemo(() => {
    if (!selectedHistoryCompany || !data.history.length) return [];
    const companyHistory = data.history.filter(c => c.company_name === selectedHistoryCompany);
    // Sort chronologically by snapshot_time
    companyHistory.sort((a, b) => new Date(a.snapshot_time) - new Date(b.snapshot_time));
    return companyHistory.map(h => ({
      date: new Date(h.snapshot_time).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }),
      solvency: parseFloat(h.solvency_ratio) || null,
      nbp: parseFloat(h.new_business_premium_cr) || null,
      csr: parseFloat(h.csr_percent) || null
    }));
  }, [data.history, selectedHistoryCompany]);

  const requestSort = (key) => {
    let direction = 'desc';
    if (sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc';
    }
    setSortConfig({ key, direction });
  };

  const SortIcon = ({ columnKey }) => {
    if (sortConfig.key !== columnKey) return null;
    return sortConfig.direction === 'asc' ? <ChevronUp size={14} className="inline ml-1" /> : <ChevronDown size={14} className="inline ml-1" />;
  };

  if (loading) {
    return <div className="loader">Loading Dynamic Market Data...</div>;
  }

  const topCompanies = data.rankings.slice(0, 5);
  
  // Prepare Main Bar Chart data dynamically based on selection
  const barChartData = data.rankings.slice(0, 10).map(c => ({
    name: c.company_name.replace(' Life Insurance', ''),
    score: parseFloat(c.composite_score || 0).toFixed(2),
    nbp: parseFloat(c.new_business_premium_cr || 0),
    csr: parseFloat(c.csr_percent || 0),
  }));

  const containerVariants = { hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.1 } } };
  const itemVariants = { hidden: { y: 20, opacity: 0 }, visible: { y: 0, opacity: 1 } };

  return (
    <div className="container">
      <motion.div className="header" initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
        <div>
          <h1 className="title-gradient">Dynamic Market Pulse</h1>
          <p className="text-muted mt-2">Interactive Intelligence & Historical Trends</p>
        </div>
        <div className="flex gap-2">
          <span className="badge badge-primary flex items-center gap-2">
            <Activity size={14} /> Live Sync
          </span>
        </div>
      </motion.div>

      {/* KPI Cards */}
      <motion.div className="grid grid-cols-4 mb-8" variants={containerVariants} initial="hidden" animate="visible">
        {[
          { title: 'Total Evaluated', val: data.latest.length, icon: Users, color: '#6366f1' },
          { title: 'Market Leader', val: topCompanies[0]?.company_name.split(' ')[0], icon: TrendingUp, color: '#ec4899' },
          { title: 'Data Snapshots', val: data.history.length, icon: History, color: '#10b981' },
          { title: 'Live Extractions', val: data.latest.filter(d => d.source === 'company_website_live').length, icon: AlertCircle, color: '#f59e0b' }
        ].map((stat, i) => (
          <motion.div key={i} className="glass-panel" variants={itemVariants}>
            <div className="flex justify-between items-center mb-4">
              <span className="text-muted font-medium">{stat.title}</span>
              <stat.icon size={20} color={stat.color} />
            </div>
            <div className="text-3xl font-bold">{stat.val}</div>
          </motion.div>
        ))}
      </motion.div>

      {/* Charts Section */}
      <div className="grid grid-cols-2 gap-6 mb-8">
        {/* Dynamic Bar Chart */}
        <motion.div className="glass-panel" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }}>
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl flex items-center gap-2">
              <BarChart3 className="text-accent" /> Top 10 Comparison
            </h2>
            <select className="dropdown" value={chartMetric} onChange={(e) => setChartMetric(e.target.value)}>
              <option value="score">Composite Score</option>
              <option value="csr">CSR %</option>
              <option value="nbp">New Business Premium</option>
            </select>
          </div>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={barChartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                <XAxis dataKey="name" stroke="#9ca3af" tick={{ fill: '#9ca3af', fontSize: 11 }} angle={-45} textAnchor="end" />
                <YAxis stroke="#9ca3af" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                <RechartsTooltip cursor={{ fill: 'rgba(255,255,255,0.05)' }} contentStyle={{ backgroundColor: '#191b24', border: '1px solid #333', borderRadius: '8px' }} />
                <Bar dataKey={chartMetric} radius={[4, 4, 0, 0]}>
                  {barChartData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={index === 0 ? '#ec4899' : '#6366f1'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>

        {/* Historical Line Chart */}
        <motion.div className="glass-panel" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }}>
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl flex items-center gap-2">
              <History className="text-success" /> Historical Trends
            </h2>
            <select className="dropdown" value={selectedHistoryCompany} onChange={(e) => setSelectedHistoryCompany(e.target.value)}>
              {data.rankings.map(c => (
                <option key={c.company_name} value={c.company_name}>{c.company_name}</option>
              ))}
            </select>
          </div>
          {historyChartData.length > 1 ? (
            <div style={{ width: '100%', height: 300 }}>
              <ResponsiveContainer>
                <LineChart data={historyChartData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" vertical={false} />
                  <XAxis dataKey="date" stroke="#9ca3af" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                  <YAxis stroke="#9ca3af" tick={{ fill: '#9ca3af', fontSize: 11 }} />
                  <RechartsTooltip contentStyle={{ backgroundColor: '#191b24', border: '1px solid #333', borderRadius: '8px' }} />
                  <Legend wrapperStyle={{ fontSize: '12px' }}/>
                  <Line type="monotone" dataKey="solvency" stroke="#10b981" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} name="Solvency Ratio" />
                  <Line type="monotone" dataKey="csr" stroke="#ec4899" strokeWidth={3} dot={{ r: 4 }} name="CSR %" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-muted flex-col gap-2 pb-10">
              <History size={32} className="opacity-50" />
              <p>Insufficient historical data points.</p>
              <p className="text-sm">Run the crawler again to build a timeline.</p>
            </div>
          )}
        </motion.div>
      </div>

      {/* Interactive Table */}
      <motion.div className="glass-panel" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl">Interactive Intelligence Explorer</h2>
          <div className="search-wrapper">
            <Search className="search-icon" size={16} />
            <input 
              type="text" 
              placeholder="Search companies..." 
              className="search-input"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
        </div>
        
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th className="clickable-th" onClick={() => requestSort('company_name')}>
                  Company <SortIcon columnKey="company_name" />
                </th>
                <th className="clickable-th" onClick={() => requestSort('source')}>
                  Source <SortIcon columnKey="source" />
                </th>
                <th className="clickable-th" onClick={() => requestSort('solvency_ratio')}>
                  Solvency <SortIcon columnKey="solvency_ratio" />
                </th>
                <th className="clickable-th" onClick={() => requestSort('csr_percent')}>
                  CSR (%) <SortIcon columnKey="csr_percent" />
                </th>
                <th className="clickable-th" onClick={() => requestSort('new_business_premium_cr')}>
                  NBP (Cr) <SortIcon columnKey="new_business_premium_cr" />
                </th>
              </tr>
            </thead>
            <tbody>
              <AnimatePresence>
                {filteredAndSortedTable.map((row) => (
                  <motion.tr 
                    key={row.company_name}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <td className="font-medium">{row.company_name}</td>
                    <td>
                      <span className={`badge ${row.source === 'company_website_live' ? 'badge-primary' : 'badge-success'}`}>
                        {row.source === 'company_website_live' ? 'Live Web' : 'IRDAI Fallback'}
                      </span>
                    </td>
                    <td>{row.solvency_ratio || '-'}</td>
                    <td>{row.csr_percent || '-'}</td>
                    <td>{row.new_business_premium_cr || '-'}</td>
                  </motion.tr>
                ))}
              </AnimatePresence>
              {filteredAndSortedTable.length === 0 && (
                <tr>
                  <td colSpan="5" className="text-center p-6 text-muted">No companies match your search.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}

export default App;
