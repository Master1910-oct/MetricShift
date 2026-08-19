import React, { useState, useEffect } from 'react';
import {
  HashRouter as Router,
  Routes,
  Route,
  Link,
  useNavigate,
  useParams,
  useLocation
} from 'react-router-dom';
import {
  Home,
  Activity,
  FileSpreadsheet,
  Users,
  CheckSquare,
  UploadCloud,
  AlertTriangle,
  CheckCircle,
  Loader2,
  Download,
  Search,
  ChevronRight,
  ChevronLeft,
  Menu
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  AreaChart,
  Area,
  PieChart,
  Pie,
  Cell
} from 'recharts';
import {
  uploadInitialDataset,
  uploadMemberUpdate,
  getPipelineStatus,
  getDashboardData,
  getPlanData,
  getPlans,
  listMembers,
  getMemberDetails,
  listMeasures,
  getOptimizationResults,
  getLatestRun,
  getDownloadUrl
} from './api/client';
import type {
  PipelineJob,
  DashboardMetrics,
  PlanDetails,
  PlanListItem,
  MembersResponse,
  MemberDetails,
  CMSMeasuresResponse,
  OptimizationResponse
} from './api/client';
import logoImg from './assets/logo.png';

// Global state for active Job ID (stored in localStorage)
const getStoredJobId = () => localStorage.getItem('ma_star_job_id') || '';
const setStoredJobId = (jobId: string) => {
  if (jobId) {
    localStorage.setItem('ma_star_job_id', jobId);
  } else {
    localStorage.removeItem('ma_star_job_id');
  }
};

// --- HELPER COMPONENT: STAR RATING ---
const StarRating: React.FC<{ rating: number }> = ({ rating }) => {
  const fullStars = Math.floor(rating);
  const hasHalf = rating % 1 !== 0;
  const starsArray = [];

  for (let i = 1; i <= 5; i++) {
    if (i <= fullStars) {
      starsArray.push('full');
    } else if (i === fullStars + 1 && hasHalf) {
      starsArray.push('half');
    } else {
      starsArray.push('empty');
    }
  }

  return (
    <div className="stars" title={`Rating: ${rating}`}>
      {starsArray.map((type, idx) => (
        <span key={idx} className={`star-item ${type}`}>
          ★
        </span>
      ))}
    </div>
  );
};

// --- GLOBAL SIDEBAR COMPONENT ---
interface SidebarProps {
  activeJobId: string;
  collapsed: boolean;
}

const NavigationSidebar: React.FC<SidebarProps> = ({ activeJobId, collapsed }) => {
  const location = useLocation();
  const path = location.pathname;

  const menuItems = [
    { name: 'Dashboard', path: '/', icon: Home, disabled: !activeJobId },
    { name: 'Data & Updates', path: '/upload', icon: UploadCloud, disabled: false },
    { name: 'Processing', path: activeJobId ? `/pipeline/${activeJobId}` : '/upload', icon: Activity, disabled: !activeJobId },
    { name: 'Optimization', path: '/optimization', icon: Activity, disabled: !activeJobId },
    { name: 'Members', path: '/members', icon: Users, disabled: !activeJobId },
    { name: 'Plans', path: '/plans', icon: FileSpreadsheet, disabled: !activeJobId },
    { name: 'CMS Measures', path: '/cms-measures', icon: CheckSquare, disabled: !activeJobId }
  ];

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-logo" style={{ padding: '20px 16px', display: 'flex', alignItems: 'center', gap: '12px' }}>
        <div style={{
          width: '48px',
          height: '48px',
          borderRadius: '10px',
          overflow: 'hidden',
          backgroundColor: '#ffffff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-start',
          border: '1.5px solid rgba(255, 255, 255, 0.15)',
          flexShrink: 0
        }}>
          <img
            src={logoImg}
            alt="Metric Shift"
            style={{
              height: '100%',
              width: 'auto',
              objectFit: 'cover',
              objectPosition: 'left',
              transform: 'scale(1.4) translateX(2px)'
            }}
          />
        </div>
        <div>
          <span className="logo-text" style={{ fontSize: '18px', fontWeight: 800, color: '#ffffff', display: 'block', lineHeight: 1.2 }}>
            Metric Shift
          </span>
          <span className="logo-sub" style={{ fontSize: '9px', opacity: 0.8, display: 'block', marginTop: '2px', lineHeight: 1.2, color: '#00e5ff' }}>
            Care Gap Detection and<br />.Star Rating Simulator.
          </span>
        </div>
      </div>
      <ul className="sidebar-menu">
        {menuItems.map((item) => {
          const isActive = path === item.path || (item.path !== '/' && path.startsWith(item.path));
          return (
            <li
              key={item.name}
              className={`sidebar-item ${isActive ? 'active' : ''} ${item.disabled ? 'disabled-link' : ''}`}
            >
              {item.disabled ? (
                <a style={{ opacity: 0.4, cursor: 'not-allowed' }} title="Please upload an Excel dataset first">
                  <item.icon size={18} />
                  <span>{item.name}</span>
                </a>
              ) : (
                <Link to={item.path}>
                  <item.icon size={18} />
                  <span>{item.name}</span>
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
};

// --- GLOBAL HEADER COMPONENT ---
interface HeaderProps {
  title: string;
  subtitle?: string;
  breadcrumbs?: string[];
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (c: boolean) => void;
}

const NavigationHeader: React.FC<HeaderProps> = ({
  title,
  subtitle,
  breadcrumbs = [],
  sidebarCollapsed,
  setSidebarCollapsed
}) => {
  const navigate = useNavigate();
  const [searchVal, setSearchVal] = useState('');

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchVal.trim()) {
      navigate(`/members?search=${encodeURIComponent(searchVal.trim())}`);
    }
  };

  const triggerUploadClick = () => {
    navigate('/upload');
  };

  return (
    <header className="header">
      <div className="header-left">
        <button
          className="header-btn menu-toggle"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          style={{ display: 'flex', marginRight: '12px' }}
          title="Toggle Navigation Sidebar"
        >
          <Menu size={20} />
        </button>
        <div className="header-title-container">
          {breadcrumbs.length > 0 && (
            <div className="breadcrumbs">
              {breadcrumbs.map((bc, idx) => (
                <React.Fragment key={idx}>
                  <span>{bc}</span>
                  {idx < breadcrumbs.length - 1 && <span className="breadcrumbs-separator">&gt;</span>}
                </React.Fragment>
              ))}
            </div>
          )}
          <h1 className="header-title" style={{ fontSize: '20px', margin: 0 }}>
            {title}
          </h1>
          {subtitle && <span className="header-subtitle">{subtitle}</span>}
        </div>
      </div>
      <div className="header-right">
        <button
          className="btn btn-primary"
          onClick={triggerUploadClick}
          style={{ padding: '8px 16px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <UploadCloud size={14} />
          <span>Upload Dataset</span>
        </button>
        <form onSubmit={handleSearch} className="global-search">
          <Search size={16} className="search-icon" />
          <input
            type="text"
            className="search-input"
            placeholder="Search member, plan, measure..."
            value={searchVal}
            onChange={(e) => setSearchVal(e.target.value)}
          />
        </form>
        <div className="profile-area">
          <div className="profile-info">
            <span className="profile-name">Admin User</span>
            <span className="profile-role">Administrator</span>
          </div>
          <div className="avatar">AD</div>
        </div>
      </div>
    </header>
  );
};

// --- UPLOAD PAGE ---
interface UploadPageProps {
  onUploadSuccess: (jobId: string) => void;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (c: boolean) => void;
}

const UploadPage: React.FC<UploadPageProps> = ({ onUploadSuccess, sidebarCollapsed, setSidebarCollapsed }) => {
  const [uploadMode, setUploadMode] = useState<'initial' | 'member_update'>('member_update');
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  const isInitial = uploadMode === 'initial';

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (!selected) return;

    const valid = selected.name.toLowerCase().endsWith('.xlsx') || selected.name.toLowerCase().endsWith('.xls');
    if (!valid) {
      setError('Please upload a valid Excel workbook (.xlsx or .xls).');
      setFile(null);
      return;
    }

    setFile(selected);
    setError(null);
    setStatusMessage(null);
  };

  const handleModeChange = (mode: 'initial' | 'member_update') => {
    setUploadMode(mode);
    setFile(null);
    setError(null);
    setStatusMessage(null);
  };

  const handleUploadSubmit = async () => {
    if (!file) return;

    setLoading(true);
    setError(null);
    setStatusMessage(
      isInitial
        ? 'Validating the complete dataset and preparing the current database...'
        : 'Validating optimized members and applying only their updates...'
    );

    try {
      const response = isInitial
        ? await uploadInitialDataset(file)
        : await uploadMemberUpdate(file);

      onUploadSuccess(response.job_id);
      navigate(`/pipeline/${response.job_id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Upload failed. Please verify the workbook and try again.');
      setStatusMessage(null);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-shell">
      <NavigationHeader
        title="Data & Updates"
        subtitle="Manage the current Medicare Advantage dataset"
        breadcrumbs={['Home', 'Data & Updates']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div className="workflow-hero">
        <div>
          <span className="eyebrow">CONTINUOUS QUALITY WORKFLOW</span>
          <h1>{isInitial ? 'Baseline Population Ingestion' : 'Post-Upload Member Dataset Updates'}</h1>
          <p>
            {isInitial
              ? 'Initial population dataset is active in Supabase. Use this mode if you wish to perform a full population re-seed.'
              : 'Initial dataset is active in Supabase. Upload resolved care gaps or updated member records to refresh the live database and run the 5-stage continuous quality optimization.'}
          </p>
        </div>
        <div className="workflow-step-count">
          <span>STATUS</span>
          <strong style={{ fontSize: '15px', color: 'var(--color-success)' }}>ACTIVE</strong>
          <small>Supabase Live</small>
        </div>
      </div>

      <div className="mode-grid">
        <button
          type="button"
          className={`mode-card ${!isInitial ? 'selected' : ''}`}
          onClick={() => handleModeChange('member_update')}
        >
          <div className="mode-card-icon update"><Users size={22} /></div>
          <div className="mode-card-copy">
            <span className="mode-card-kicker">RECOMMENDED / ACTIVE CYCLE</span>
            <h3>Member Update</h3>
            <p>Upload care-gap resolutions & updated member records for the live population.</p>
          </div>
          <span className="mode-card-radio">{!isInitial ? '✓' : ''}</span>
        </button>

        <button
          type="button"
          className={`mode-card ${isInitial ? 'selected' : ''}`}
          onClick={() => handleModeChange('initial')}
        >
          <div className="mode-card-icon"><FileSpreadsheet size={22} /></div>
          <div className="mode-card-copy">
            <span className="mode-card-kicker">FULL RE-SEED</span>
            <h3>Baseline Dataset</h3>
            <p>Full 8-sheet workbook to completely re-seed the baseline population.</p>
          </div>
          <span className="mode-card-radio">{isInitial ? '✓' : ''}</span>
        </button>
      </div>

      <div className="upload-workspace">
        <div className="upload-main card">
          <div className="section-heading">
            <div>
              <span className="section-kicker">{isInitial ? 'BASELINE LOAD' : 'TARGETED UPDATE'}</span>
              <h2>{isInitial ? 'Upload the complete dataset' : 'Upload optimized member updates'}</h2>
            </div>
            <span className={`workflow-badge ${isInitial ? 'baseline' : 'update'}`}>
              {isInitial ? 'Current database' : 'Authorized members only'}
            </span>
          </div>

          <div className="upload-explainer">
            {isInitial ? (
              <>
                <strong>Required workbook:</strong> PLANS, PLAN_BENEFITS, MEMBERS, MEMBER_ENROLLMENT,
                MEMBER_HISTORY, CMS_MEASURES, PLAN_MEASURE_PERFORMANCE and PART_D_MEDICATION_HISTORY.
              </>
            ) : (
              <>
                <strong>Important:</strong> every uploaded member ID must belong to the latest completed
                optimization. Unauthorized members cause the entire upload to be rejected.
              </>
            )}
          </div>

          <label
            className={`upload-dropzone-modern ${file ? 'has-file' : ''}`}
            htmlFor="file-upload-input-page"
          >
            <div className="upload-drop-icon">
              {file ? <CheckCircle size={28} /> : <UploadCloud size={28} />}
            </div>
            <div className="upload-drop-copy">
              <strong>{file ? file.name : 'Choose an Excel workbook'}</strong>
              <span>
                {file
                  ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready to process`
                  : 'Click to browse · .xlsx or .xls · Maximum 50 MB'}
              </span>
            </div>
            <span className="upload-browse">Browse</span>
            <input
              id="file-upload-input-page"
              type="file"
              accept=".xlsx,.xls"
              onChange={handleFileChange}
            />
          </label>

          {statusMessage && loading && (
            <div className="inline-status processing">
              <Loader2 size={17} className="stage-icon running" />
              <span>{statusMessage}</span>
            </div>
          )}

          {error && (
            <div className="inline-status error">
              <AlertTriangle size={17} />
              <span>{error}</span>
            </div>
          )}

          <div className="upload-actions">
            {file && (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setFile(null)}
                disabled={loading}
              >
                Remove file
              </button>
            )}
            <button
              type="button"
              className="btn btn-primary upload-submit"
              onClick={handleUploadSubmit}
              disabled={!file || loading}
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="stage-icon running" />
                  Processing...
                </>
              ) : (
                <>
                  {isInitial ? 'Start baseline pipeline' : 'Apply updates & run pipeline'}
                  <ChevronRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>

        <aside className="upload-side-panel">
          <div className="side-card">
            <span className="section-kicker">WHAT HAPPENS NEXT</span>
            <ol className="workflow-list">
              <li><span>1</span><div><strong>Validate</strong><small>Workbook and member authorization</small></div></li>
              <li><span>2</span><div><strong>Update database</strong><small>Only permitted source records change</small></div></li>
              <li><span>3</span><div><strong>Run pipeline</strong><small>Rule engine through final report</small></div></li>
            </ol>
          </div>

          <div className="side-card muted">
            <div className="side-card-title"><CheckCircle size={17} /> Protected by design</div>
            <p>
              Member updates do not replace the current database. Records that are not included in the
              upload remain untouched.
            </p>
          </div>
        </aside>
      </div>
    </div>
  );
};

// --- PIPELINE PROCESSING PAGE ---
const PipelinePage: React.FC = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const [jobState, setJobState] = useState<PipelineJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!jobId) return;

    let isDone = false;
    let dashboardFetched = false;

    const checkStatus = async () => {
      if (isDone) return;
      try {
        const status = await getPipelineStatus(jobId);
        setJobState(status);

        if (status.status === 'completed') {
          isDone = true;
          setStoredJobId(jobId);
          if (!dashboardFetched) {
            dashboardFetched = true;
            try {
              const data = await getDashboardData(jobId);
              setMetrics(data);
            } catch (e) {
              // Non-critical summary preview
            }
          }
        } else if (status.status === 'failed') {
          isDone = true;
          setError(status.error || 'Execution pipeline failed.');
        }
      } catch (err: any) {
        setError('Error fetching pipeline status.');
      }
    };

    checkStatus();
    const interval = setInterval(() => {
      if (!isDone) {
        checkStatus();
      } else {
        clearInterval(interval);
      }
    }, 2500);

    return () => {
      isDone = true;
      clearInterval(interval);
    };
  }, [jobId]);

  // Exactly 5 visible business stages (Requirement 11)
  const visibleStages = [
    { key: 'file_upload', label: '1. File Upload' },
    { key: 'rule_engine', label: '2. Rule Based Engine' },
    { key: 'ml_model', label: '3. ML Model' },
    { key: 'optimization', label: '4. Optimization' },
    { key: 'final_report', label: '5. Final Member Report' },
  ];

  const getStageStatus = (key: string): 'pending' | 'running' | 'completed' | 'failed' => {
    if (!jobState || !jobState.stages) return 'pending';
    const s = jobState.stages;

    if (key === 'file_upload') {
      return s.file_upload?.status || 'pending';
    }
    if (key === 'rule_engine') {
      return s.rule_engine?.status || 'pending';
    }
    if (key === 'ml_model') {
      const mlKeys = ['candidate_generation', 'ml_inference', 'calibration', 'intervention_selection'];
      if (mlKeys.some((k) => s[k]?.status === 'failed')) return 'failed';
      if (mlKeys.every((k) => s[k]?.status === 'completed')) return 'completed';
      if (mlKeys.some((k) => s[k]?.status === 'running' || s[k]?.status === 'completed')) return 'running';
      return 'pending';
    }
    if (key === 'optimization') {
      const optKeys = ['milp_optimization', 'star_rating_contribution'];
      if (optKeys.some((k) => s[k]?.status === 'failed')) return 'failed';
      if (optKeys.every((k) => s[k]?.status === 'completed')) return 'completed';
      if (optKeys.some((k) => s[k]?.status === 'running' || s[k]?.status === 'completed')) return 'running';
      return 'pending';
    }
    if (key === 'final_report') {
      return s.final_report?.status || 'pending';
    }
    return 'pending';
  };

  const getStageMessage = (key: string): string => {
    if (!jobState || !jobState.stages) return 'Waiting';
    const s = jobState.stages;

    if (key === 'file_upload') return s.file_upload?.message || 'Waiting';
    if (key === 'rule_engine') return s.rule_engine?.message || 'Waiting';
    if (key === 'ml_model') {
      const mlKeys = ['intervention_selection', 'calibration', 'ml_inference', 'candidate_generation'];
      for (const k of mlKeys) {
        if (s[k]?.status === 'running') return s[k]?.message || 'Running ML Model...';
        if (s[k]?.status === 'failed') return s[k]?.message || 'ML Model failed.';
      }
      if (s.intervention_selection?.status === 'completed') {
        return s.intervention_selection?.message || 'ML prediction & intervention selection completed';
      }
      return s.candidate_generation?.message || 'Waiting';
    }
    if (key === 'optimization') {
      const optKeys = ['star_rating_contribution', 'milp_optimization'];
      for (const k of optKeys) {
        if (s[k]?.status === 'running') return s[k]?.message || 'Running Optimization...';
        if (s[k]?.status === 'failed') return s[k]?.message || 'Optimization failed.';
      }
      if (s.star_rating_contribution?.status === 'completed') {
        return s.star_rating_contribution?.message || 'Optimization completed';
      }
      return s.milp_optimization?.message || 'Waiting';
    }
    if (key === 'final_report') return s.final_report?.message || 'Waiting';
    return 'Waiting';
  };

  const getStageRows = (key: string): number | null | undefined => {
    if (!jobState || !jobState.stages) return null;
    const s = jobState.stages;
    if (key === 'file_upload') return s.file_upload?.rows;
    if (key === 'rule_engine') return s.rule_engine?.rows;
    if (key === 'ml_model') return s.intervention_selection?.rows ?? s.ml_inference?.rows ?? s.candidate_generation?.rows;
    if (key === 'optimization') return s.milp_optimization?.rows;
    if (key === 'final_report') return s.final_report?.rows;
    return null;
  };

  return (
    <div className="pipeline-screen card" style={{ maxWidth: '680px', margin: '40px auto' }}>
      <div className="pipeline-header">
        <h2 className="pipeline-title">Processing Your Dataset</h2>
        <p style={{ color: 'var(--color-text-muted)', fontSize: '13px', marginTop: '4px' }}>
          Job ID: {jobId}
        </p>
      </div>

      <div className="pipeline-stages">
        {visibleStages.map((stage) => {
          const status = getStageStatus(stage.key);
          const message = getStageMessage(stage.key);
          const rows = getStageRows(stage.key);

          return (
            <div key={stage.key} className={`pipeline-stage ${status === 'running' ? 'running' : ''}`}>
              <div className={`stage-icon ${status}`}>
                {status === 'completed' && <CheckCircle size={16} />}
                {status === 'failed' && <AlertTriangle size={16} />}
                {status === 'running' && <Loader2 size={16} className="stage-icon running" />}
                {status === 'pending' && <span style={{ fontSize: '10px' }}>○</span>}
              </div>
              <div className="stage-info" style={{ flex: 1 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span className="stage-name">{stage.label}</span>
                  {rows != null && (
                    <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--color-primary)' }}>
                      {rows.toLocaleString()} rows
                    </span>
                  )}
                </div>
                <span className="stage-message">{message}</span>
              </div>
            </div>
          );
        })}
      </div>

      {error && (
        <div className="pipeline-stage failed" style={{ marginTop: '20px', gap: '12px' }}>
          <AlertTriangle className="stage-icon failed" />
          <span style={{ fontSize: '14px', color: 'var(--color-danger)' }}>{error}</span>
        </div>
      )}

      {jobState?.status === 'completed' && metrics && (
        <div className="card" style={{ marginTop: '24px', backgroundColor: 'var(--color-success-light)', border: '1px solid rgba(16, 185, 129, 0.2)', padding: '20px' }}>
          <h4 style={{ color: 'var(--color-success)', fontWeight: 700, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle size={18} />
            <span>Pipeline Completed Successfully!</span>
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '13px', textAlign: 'left', color: 'var(--color-text-dark)' }}>
            <div><strong>Total Active Plans:</strong> {metrics.summary?.total_plans ?? '—'}</div>
            <div><strong>Total Members Processed:</strong> {(metrics.summary?.total_members ?? 0).toLocaleString()}</div>
            <div><strong>Open Care Gaps:</strong> {(metrics.summary?.open_care_gaps ?? 0).toLocaleString()}</div>
            <div><strong>CMS Quality Measures:</strong> {metrics.summary?.cms_measures ?? '—'}</div>
          </div>
        </div>
      )}

      {jobState?.status === 'completed' && (
        <div style={{ marginTop: '32px', display: 'flex', justifyContent: 'center', gap: '12px', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={() => navigate('/')}>
            View Dashboard
          </button>
          <button className="btn btn-secondary" onClick={() => navigate('/optimization')}>
            Outreach Optimization
          </button>
          <button className="btn btn-secondary" onClick={() => navigate('/members')}>
            Member Directory
          </button>
          <a
            href={getDownloadUrl(jobId || '')}
            className="btn btn-secondary"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', textDecoration: 'none' }}
            download="final_member_report.xlsx"
          >
            <Download size={15} />
            <span>Download Report (.xlsx)</span>
          </a>
        </div>
      )}

      {jobState?.status === 'failed' && (
        <div style={{ marginTop: '32px', textAlign: 'center' }}>
          <button className="btn btn-secondary" onClick={() => navigate('/upload')}>
            Retry Upload
          </button>
        </div>
      )}
    </div>
  );
};

// --- HOME DASHBOARD ---
interface DashboardProps {
  jobId: string;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (c: boolean) => void;
}

const HomeDashboard: React.FC<DashboardProps> = ({ jobId, sidebarCollapsed, setSidebarCollapsed }) => {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [planId, setPlanId] = useState<string>('');
  const [loading, setLoading] = useState(true);

  // Fetch on mount or when jobId changes
  useEffect(() => {
    let cancelled = false;
    const fetchMetrics = async () => {
      setLoading(true);
      try {
        const data = await getDashboardData(jobId, undefined);
        if (!cancelled) {
          setMetrics(data);
          // Set first plan as selected without triggering re-fetch loop
          if (data.plan_performances?.length) {
            setPlanId(data.plan_performances[0].plan_id);
          }
        }
      } catch (err) {
        console.error('Dashboard fetch error:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchMetrics();
    return () => { cancelled = true; };
  }, [jobId]);

  if (loading && !metrics) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading analytics...</span></div>;
  }

  if (!metrics) {
    return <div className="empty-state">No dashboard analytics found.</div>;
  }

  const defaultFirstPlan = metrics.plan_performances?.[0]?.plan_id || '';

  return (
    <div>
      <NavigationHeader
        title="Home Dashboard"
        subtitle="Care Gap Detection & Star Rating Simulator"
        breadcrumbs={['Metric Shift']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      {/* Title Row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text-dark)', margin: 0 }}>Clinical Performance Overview</h2>
      </div>

      {/* Summary Cards */}
      <div className="summary-grid">
        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
            <FileSpreadsheet />
          </div>
          <div className="card-info">
            <span className="card-label">Total Plans</span>
            <span className="card-value">{metrics.summary?.total_plans ?? '—'}</span>
            <span className="card-subtext">Medicare Advantage Plans</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-success-light)', color: 'var(--color-success)' }}>
            <Users />
          </div>
          <div className="card-info">
            <span className="card-label">Total Members</span>
            <span className="card-value">{(metrics.summary?.total_members ?? 0).toLocaleString()}</span>
            <span className="card-subtext">Enrolled Members</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
            <AlertTriangle />
          </div>
          <div className="card-info">
            <span className="card-label">Open Care Gaps</span>
            <span className="card-value">{(metrics.summary?.open_care_gaps ?? 0).toLocaleString()}</span>
            <span className="card-subtext">Care Gaps Identified</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-purple-light)', color: 'var(--color-purple)' }}>
            <CheckSquare />
          </div>
          <div className="card-info">
            <span className="card-label">CMS Measures</span>
            <span className="card-value">{metrics.summary?.cms_measures ?? '—'}</span>
            <span className="card-subtext">Quality Measure Specifications</span>
          </div>
        </div>
      </div>

      {/* Star Rating Simulation Highlight */}
      <div className="card" style={{ marginBottom: '24px', backgroundColor: '#f0fdf4', border: '1.5px solid #86efac', padding: '18px 24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <span style={{ fontSize: '11px', fontWeight: 700, color: '#15803d', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              STAR RATING SIMULATION & PROJECTION
            </span>
            <h3 style={{ fontSize: '17px', fontWeight: 700, color: '#14532d', margin: '4px 0 2px' }}>
              Projected Star Rating Impact from Prioritized Member Resolutions
            </h3>
            <p style={{ fontSize: '13px', color: '#166534', margin: 0 }}>
              Simulated improvement if prioritized member care gaps are resolved through recommended interventions.
            </p>
          </div>
          <div style={{ display: 'flex', gap: '24px', alignItems: 'center' }}>
            <div style={{ textAlign: 'center' }}>
              <span style={{ fontSize: '11px', color: '#166534', display: 'block', fontWeight: 600 }}>Targeted Members</span>
              <strong style={{ fontSize: '20px', color: '#14532d' }}>{metrics.summary?.selected_members ?? 250}</strong>
            </div>
            <div style={{ textAlign: 'center', borderLeft: '1.5px solid #bbf7d0', paddingLeft: '24px' }}>
              <span style={{ fontSize: '11px', color: '#166534', display: 'block', fontWeight: 600 }}>Projected Star Gain</span>
              <strong style={{ fontSize: '20px', color: '#15803d' }}>
                +{((metrics.summary?.total_star_contribution ?? 0.3037)).toFixed(4)}★
              </strong>
            </div>
          </div>
        </div>
      </div>

      {/* Charts Grid */}
      <div className="dashboard-grid-2">
        <div className="card">
          <h3 className="card-title">Care Gaps by Plan</h3>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics.gaps_by_plan || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="plan_id" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="gaps" fill="#8884d8" radius={[4, 4, 0, 0]} label={{ position: 'top' }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Plan Performance (Star Rating)</h3>
          <div className="table-container" style={{ border: 'none', marginTop: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Plan ID</th>
                  <th>Plan Name</th>
                  <th>Star Rating</th>
                  <th>Rating Value</th>
                </tr>
              </thead>
              <tbody>
                {(metrics.plan_performances || []).map((perf) => (
                  <tr key={perf.plan_id}>
                    <td style={{ fontWeight: 600 }}>{perf.plan_id}</td>
                    <td>{perf.plan_name}</td>
                    <td><StarRating rating={perf.rating} /></td>
                    <td style={{ fontWeight: 700 }}>{perf.rating.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-3" style={{ marginBottom: '24px' }}>
        <div className="card">
          <h3 className="card-title">Plan Star Rating Trend</h3>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics.improvement_trend || []}>
                <defs>
                  <linearGradient id="colorRating" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#1e52e8" stopOpacity={0.8} />
                    <stop offset="95%" stopColor="#1e52e8" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="year" />
                <YAxis domain={[2.0, 5.0]} />
                <Tooltip />
                <Area type="monotone" dataKey="rating" stroke="#1e52e8" fillOpacity={1} fill="url(#colorRating)" label={{ position: 'top' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Select Plan</h3>
          <div className="form-group" style={{ marginBottom: '24px' }}>
            <label className="form-label">Plan Filter</label>
            <select
              className="form-select"
              value={planId}
              onChange={(e) => setPlanId(e.target.value)}
            >
              {(metrics.plan_performances || []).map((p) => (
                <option key={p.plan_id} value={p.plan_id}>
                  {p.plan_id} - {p.plan_name}
                </option>
              ))}
            </select>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Selected Plan:</span>
              <span style={{ fontWeight: 600 }}>{planId}</span>
            </div>
            <button className="btn btn-secondary" style={{ width: '100%' }} onClick={() => setPlanId(defaultFirstPlan)}>
              Clear Filter
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- PLANS PAGE ---
interface PageProps {
  jobId: string;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (c: boolean) => void;
}

const PlansPage: React.FC<PageProps> = ({ jobId, sidebarCollapsed, setSidebarCollapsed }) => {
  const [planId, setPlanId] = useState<string>('');
  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [data, setData] = useState<PlanDetails | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadPlans = async () => {
      try {
        const list = await getPlans(jobId);
        setPlans(list);
        if (list.length > 0 && !planId) {
          setPlanId(list[0].plan_id);
        }
      } catch (e) {
        console.error(e);
      }
    };
    loadPlans();
  }, [jobId]);

  useEffect(() => {
    if (!planId) return;
    const fetchPlanData = async () => {
      setLoading(true);
      try {
        const details = await getPlanData(jobId, planId);
        setData(details);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchPlanData();
  }, [jobId, planId]);

  if (loading && !data) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading plan profiles...</span></div>;
  }

  if (!data) {
    return <div className="empty-state">No plan details found.</div>;
  }

  return (
    <div>
      <NavigationHeader
        title="Plans"
        subtitle="Detailed quality and enrollment configurations"
        breadcrumbs={['Home', 'Plans']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div className="card" style={{ marginBottom: '24px', padding: '16px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontWeight: 600, fontSize: '14px' }}>Select Plan:</span>
          <select
            className="form-select"
            style={{ width: '280px' }}
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
          >
            {plans.map((p) => (
              <option key={p.plan_id} value={p.plan_id}>
                {p.plan_id} - {p.plan_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="summary-grid">
        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
            <Users />
          </div>
          <div className="card-info">
            <span className="card-label">Total Members</span>
            <span className="card-value">{(data.summary?.total_members ?? 0).toLocaleString()}</span>
            <span className="card-subtext">Enrolled Members</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
            <AlertTriangle />
          </div>
          <div className="card-info">
            <span className="card-label">Open Care Gaps</span>
            <span className="card-value">{(data.summary?.open_care_gaps ?? 0).toLocaleString()}</span>
            <span className="card-subtext">Members with Open Gaps</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-purple-light)', color: 'var(--color-purple)' }}>
            <CheckSquare />
          </div>
          <div className="card-info">
            <span className="card-label">Care Gaps</span>
            <span className="card-value">{(data.summary?.total_care_gaps ?? 0).toLocaleString()}</span>
            <span className="card-subtext">Total Gaps Identified</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-success-light)', color: 'var(--color-success)' }}>
            <Activity />
          </div>
          <div className="card-info">
            <span className="card-label">Plan Rating</span>
            <div className="card-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>{data.summary.plan_rating.toFixed(1)}</span>
              <StarRating rating={data.summary.plan_rating} />
            </div>
            <span className="card-subtext">Overall Star Rating</span>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-2">
        <div className="card">
          <h3 className="card-title">Care Gaps by Status</h3>
          <div style={{ height: '300px', display: 'flex', justifyContent: 'center' }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data.gaps_by_status}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={5}
                  dataKey="value"
                >
                  <Cell fill="var(--color-danger)" />
                  <Cell fill="var(--color-success)" />
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Care Gaps Resolved Over Time</h3>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.resolved_over_time || []}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="year" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="resolved" fill="#1e52e8" radius={[4, 4, 0, 0]} label={{ position: 'top' }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-2" style={{ marginBottom: '24px' }}>
        <div className="card">
          <h3 className="card-title">Star Rating Improvement Over Time</h3>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.improvement_trend}>
                <defs>
                  <linearGradient id="colorRatingPlan" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.8} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="year" />
                <YAxis domain={[2.0, 5.0]} />
                <Tooltip />
                <Area type="monotone" dataKey="rating" stroke="#10b981" fillOpacity={1} fill="url(#colorRatingPlan)" label={{ position: 'top' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Plan Details</h3>
          <div className="table-container" style={{ border: 'none', marginTop: 0 }}>
            <table className="data-table">
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan ID</td>
                  <td style={{ fontWeight: 700 }}>{data.details?.plan_id ?? '—'}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan Name</td>
                  <td>{data.details?.plan_name ?? '—'}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Contract ID</td>
                  <td>{data.details?.contract_id ?? '—'}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan Type</td>
                  <td>{data.details?.plan_type ?? '—'}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>County</td>
                  <td>{data.details?.county ?? '—'}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Rating Year</td>
                  <td>{data.details?.rating_year ?? '—'}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Start Date</td>
                  <td>{data.details?.start_date ?? '—'}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- MEMBERS PAGE ---
const MembersPage: React.FC<PageProps> = ({ jobId, sidebarCollapsed, setSidebarCollapsed }) => {
  const [data, setData] = useState<MembersResponse | null>(null);
  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [planId, setPlanId] = useState('');
  const [gender, setGender] = useState('');
  const [search, setSearch] = useState('');
  const [minAge, setMinAge] = useState('');
  const [maxAge, setMaxAge] = useState('');

  const loc = useLocation();

  useEffect(() => {
    const loadPlans = async () => {
      try {
        const list = await getPlans(jobId);
        setPlans(list);
      } catch (e) {
        console.error(e);
      }
    };
    loadPlans();
  }, [jobId]);

  const fetchMembers = async (currentPage = 1) => {
    setLoading(true);
    try {
      const queryParams = new URLSearchParams(loc.search);
      const searchParam = queryParams.get('search') || search;

      const res = await listMembers(jobId, {
        page: currentPage,
        limit: 10,
        plan_id: planId || undefined,
        gender: gender || undefined,
        search: searchParam || undefined,
        min_age: minAge ? parseInt(minAge) : undefined,
        max_age: maxAge ? parseInt(maxAge) : undefined
      });
      setData(res);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const queryParams = new URLSearchParams(loc.search);
    const searchParam = queryParams.get('search');
    if (searchParam) {
      setSearch(searchParam);
    }
    fetchMembers(page);
  }, [jobId, page, loc.search]);

  const handleApplyFilters = () => {
    setPage(1);
    fetchMembers(1);
  };

  const handleClearFilters = () => {
    setPlanId('');
    setGender('');
    setMinAge('');
    setMaxAge('');
    setSearch('');
    setPage(1);
    window.history.pushState({}, '', window.location.pathname);

    setTimeout(() => {
      fetchMembers(1);
    }, 100);
  };

  if (loading && !data) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading members...</span></div>;
  }

  return (
    <div>
      <NavigationHeader
        title="Members"
        subtitle="Patient demographic and clinical registry"
        breadcrumbs={['Home', 'Members']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      {/* Filter panel */}
      <div className="filter-panel">
        <div className="form-group">
          <label className="form-label">Plan ID</label>
          <select className="form-select" value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">All Plans</option>
            {plans.map((p) => (
              <option key={p.plan_id} value={p.plan_id}>
                {p.plan_id} - {p.plan_name}
              </option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Gender</label>
          <select className="form-select" value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="">All Genders</option>
            <option value="M">Male</option>
            <option value="F">Female</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Min Age</label>
          <input
            type="number"
            className="form-input"
            placeholder="Min Age"
            value={minAge}
            onChange={(e) => setMinAge(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Max Age</label>
          <input
            type="number"
            className="form-input"
            placeholder="Max Age"
            value={maxAge}
            onChange={(e) => setMaxAge(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Search Name/ID</label>
          <input
            type="text"
            className="form-input"
            placeholder="Search..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="filter-actions">
          <button className="btn btn-secondary" onClick={handleClearFilters}>
            Clear
          </button>
          <button className="btn btn-primary" onClick={handleApplyFilters}>
            Apply
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '24px' }}>
        <h3 className="card-title">Member Directory</h3>

        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center' }}><Loader2 className="stage-icon running" style={{ margin: '0 auto' }} /></div>
        ) : !data || data.records.length === 0 ? (
          <div className="empty-state">No members matched the criteria.</div>
        ) : (
          <>
            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Member ID</th>
                    <th>Name</th>
                    <th>DOB</th>
                    <th>Age</th>
                    <th>Gender</th>
                    <th>Condition</th>
                    <th>Health Plan</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {data.records.map((member, index) => (
                    <tr key={`${member.member_id}-${member.plan_id}-${index}`}>
                      <td style={{ fontWeight: 600 }}>{member.member_id}</td>
                      <td style={{ textTransform: 'capitalize' }}>{member.member_name}</td>
                      <td>{member.dob}</td>
                      <td>{member.age}</td>
                      <td>{member.gender}</td>
                      <td>{member.condition}</td>
                      <td><span className="status-badge closed" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>{member.plan_id}</span></td>
                      <td>
                        <Link to={`/members/${member.member_id}`} className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }}>
                          View Details
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="pagination">
              <button
                className="page-btn"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft size={16} />
              </button>

              {Array.from({ length: data.pagination.total_pages }, (_, i) => i + 1)
                .slice(Math.max(0, page - 3), Math.min(data.pagination.total_pages, page + 2))
                .map((p) => (
                  <button
                    key={p}
                    className={`page-btn ${p === page ? 'active' : ''}`}
                    onClick={() => setPage(p)}
                  >
                    {p}
                  </button>
                ))}

              <button
                className="page-btn"
                onClick={() => setPage((p) => Math.min(data.pagination.total_pages, p + 1))}
                disabled={page === data.pagination.total_pages}
              >
                <ChevronRight size={16} />
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// --- MEMBER DETAILS PAGE ---
const MemberDetailsPage: React.FC<PageProps> = ({ jobId, sidebarCollapsed, setSidebarCollapsed }) => {
  const { memberId } = useParams<{ memberId: string }>();
  const [data, setData] = useState<MemberDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    if (!memberId) return;
    const fetchDetails = async () => {
      setLoading(true);
      try {
        const details = await getMemberDetails(jobId, memberId);
        setData(details);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchDetails();
  }, [jobId, memberId]);

  if (loading) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading member profile...</span></div>;
  }

  if (!data) {
    return <div className="empty-state">Member profile details not found.</div>;
  }

  return (
    <div>
      <NavigationHeader
        title="Member Details"
        subtitle="Clinical and priority care-gap chart"
        breadcrumbs={['Home', 'Members', 'Member Details']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div style={{ marginBottom: '20px' }}>
        <button className="btn btn-secondary" onClick={() => navigate('/members')}>
          ← Back to Members
        </button>
      </div>

      {/* Main card */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
            <div className="avatar" style={{ width: '64px', height: '64px', fontSize: '24px' }}>
              {data.member_name.split(' ').map((n) => n[0]).join('').toUpperCase()}
            </div>
            <div>
              <h2 style={{ fontSize: '22px', textTransform: 'capitalize', marginBottom: '4px' }}>{data.member_name}</h2>
              <span style={{ color: 'var(--color-text-muted)', fontSize: '14px' }}>ID: {data.member_id}</span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Overall Priority</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px' }}>
              <span className={`priority-badge ${data.overall_priority.toLowerCase()}`}>{data.overall_priority}</span>
              <span style={{ fontSize: '18px', fontWeight: 800 }}>{data.priority_score}% score</span>
            </div>
          </div>
        </div>

        <hr style={{ border: 'none', borderTop: '1px solid var(--color-border)', margin: '24px 0' }} />

        <h3 style={{ fontSize: '16px', marginBottom: '16px' }}>Patient Details</h3>
        <div className="dashboard-grid-2" style={{ gap: '40px' }}>
          <div>
            <table className="data-table" style={{ border: 'none' }}>
              <tbody>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Member ID</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.member_id}</td>
                </tr>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Health Plan (Enrolled)</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.health_plan || '—'}</td>
                </tr>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Date of Birth</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.dob || '—'}</td>
                </tr>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Age</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.age ?? '—'}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div>
            <table className="data-table" style={{ border: 'none' }}>
              <tbody>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Gender</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.gender || '—'}</td>
                </tr>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Chronic Conditions</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.conditions || '—'}</td>
                </tr>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Enrollment Date</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.enrollment_date || '—'}</td>
                </tr>
                <tr>
                  <td style={{ border: 'none', padding: '8px 0', color: 'var(--color-text-muted)', fontWeight: 500 }}>Plan Type</td>
                  <td style={{ border: 'none', padding: '8px 0', fontWeight: 600 }}>{data.details?.plan_type || '—'}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-2" style={{ marginBottom: '24px' }}>
        <div className="card">
          <h3 className="card-title">Care Gap Summary</h3>
          <div style={{ display: 'flex', gap: '20px', marginTop: '12px' }}>
            <div className="stat-box danger" style={{ flex: 1 }}>
              <span style={{ fontSize: '12px', color: 'var(--color-danger)', fontWeight: 700, textTransform: 'uppercase' }}>Open Care Gaps</span>
              <h4 style={{ fontSize: '32px', color: 'var(--color-danger)', margin: '8px 0' }}>{data.gaps_summary.open_care_gaps}</h4>
              <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>High Priority: {data.gaps_summary.high_priority_gaps}</span>
            </div>
            <div className="stat-box success" style={{ flex: 1 }}>
              <span style={{ fontSize: '12px', color: 'var(--color-success)', fontWeight: 700, textTransform: 'uppercase' }}>Closed Care Gaps</span>
              <h4 style={{ fontSize: '32px', color: 'var(--color-success)', margin: '8px 0' }}>{data.gaps_summary.closed_care_gaps}</h4>
              <span style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>Closed This Year</span>
            </div>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Gaps in Selected Plan</h3>
          <div className="table-container" style={{ border: 'none', marginTop: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Care Gap Name</th>
                  <th>Measure ID</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.care_gaps.map((gap, index) => (
                  <tr key={index}>
                    <td style={{ fontWeight: 600 }}>{gap.care_gap_name}</td>
                    <td>{gap.measure_id}</td>
                    <td>
                      <span className={`status-badge ${gap.status.toLowerCase()}`}>
                        {gap.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

// --- CMS MEASURES PAGE ---
const CMSMeasuresPage: React.FC<PageProps> = ({ jobId, sidebarCollapsed, setSidebarCollapsed }) => {
  const [data, setData] = useState<CMSMeasuresResponse | null>(null);
  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [planId, setPlanId] = useState('');

  useEffect(() => {
    const loadPlans = async () => {
      try {
        const list = await getPlans(jobId);
        setPlans(list);
        if (list.length > 0 && !planId) {
          setPlanId(list[0].plan_id);
        }
      } catch (e) {
        console.error(e);
      }
    };
    loadPlans();
  }, [jobId]);

  useEffect(() => {
    const fetchMeasures = async () => {
      setLoading(true);
      try {
        const res = await listMeasures(jobId);
        setData(res);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchMeasures();
  }, [jobId]);

  if (loading && !data) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading measures list...</span></div>;
  }

  if (!data) {
    return <div className="empty-state">CMS measures not found.</div>;
  }

  return (
    <div>
      <NavigationHeader
        title="CMS Measures"
        subtitle="Quality specifications registry"
        breadcrumbs={['Home', 'CMS Measures']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div className="card" style={{ marginBottom: '24px', padding: '16px 24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontWeight: 600, fontSize: '14px' }}>Plan Filter:</span>
          <select
            className="form-select"
            style={{ width: '280px' }}
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
          >
            {plans.map((p) => (
              <option key={p.plan_id} value={p.plan_id}>
                {p.plan_id} - {p.plan_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="summary-grid-3">
        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
            <CheckSquare />
          </div>
          <div className="card-info">
            <span className="card-label">Total Measures</span>
            <span className="card-value">{data.summary.total_measures}</span>
            <span className="card-subtext">Measures used in this plan</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
            <AlertTriangle />
          </div>
          <div className="card-info">
            <span className="card-label">High Priority Measures</span>
            <span className="card-value">{data.summary.high_priority_measures}</span>
            <span className="card-subtext">Require attention</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-purple-light)', color: 'var(--color-purple)' }}>
            <Activity />
          </div>
          <div className="card-info">
            <span className="card-label">Rating Year</span>
            <span className="card-value">{data.summary.rating_year}</span>
            <span className="card-subtext">CMS Evaluation Schedule</span>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '24px' }}>
        <h3 className="card-title">Measures Used in Plan: {planId}</h3>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '80px' }}>Part</th>
                <th>Measure ID</th>
                <th>Measure Name</th>
                <th>Measure Type</th>
                <th>Domain</th>
                <th>Measure ID Value</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {data.records.map((measure, index) => (
                <tr key={index}>
                  <td>
                    <span className="status-badge closed" style={{ backgroundColor: measure.part === 'C' ? 'var(--color-primary-light)' : 'var(--color-success-light)', color: measure.part === 'C' ? 'var(--color-primary)' : 'var(--color-success)' }}>
                      {measure.part}
                    </span>
                  </td>
                  <td style={{ fontWeight: 600 }}>{measure.measure_id}</td>
                  <td>{measure.measure_name}</td>
                  <td>{measure.measure_type}</td>
                  <td>{measure.domain}</td>
                  <td style={{ fontWeight: 600 }}>{measure.measure_id_value}</td>
                  <td style={{ fontSize: '12px', color: 'var(--color-text-muted)', maxWidth: '300px' }}>
                    {measure.description}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// --- OPTIMIZATION PAGE ---
const OptimizationPage: React.FC<PageProps> = ({ jobId, sidebarCollapsed, setSidebarCollapsed }) => {
  const [planId, setPlanId] = useState('');
  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [results, setResults] = useState<OptimizationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadPlans = async () => {
      try {
        const list = await getPlans(jobId);
        setPlans(list);
      } catch (e) {
        console.error(e);
      }
    };
    loadPlans();
  }, [jobId]);

  const loadResults = async (selectedPlan: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await getOptimizationResults(jobId, selectedPlan);
      setResults(res);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load optimization results.');
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResults(planId);
  }, [jobId, planId]);

  return (
    <div>
      <NavigationHeader
        title="Outreach Optimization"
        subtitle="Optimal candidate selection calculated by Mixed-Integer Linear Programming"
        breadcrumbs={['Home', 'Optimization']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      {/* Control & Filter panel */}
      <div className="filter-panel" style={{ gridTemplateColumns: 'minmax(240px, 1fr) auto', alignItems: 'flex-end' }}>
        <div className="form-group">
          <label className="form-label">Filter by Plan</label>
          <select className="form-select" value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">All Plans (All Top Prioritized Members)</option>
            {plans.map((p) => (
              <option key={p.plan_id} value={p.plan_id}>
                {p.plan_id} - {p.plan_name}
              </option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          {planId && (
            <button className="btn btn-secondary" onClick={() => setPlanId('')}>
              Show All Plans
            </button>
          )}
          <a
            href={getDownloadUrl(jobId)}
            className="btn btn-primary"
            style={{ display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}
            download="final_member_report.xlsx"
          >
            <Download size={16} />
            <span>Download Final Report (.xlsx)</span>
          </a>
        </div>
      </div>

      {error && (
        <div className="pipeline-stage failed" style={{ marginBottom: '24px', gap: '12px' }}>
          <AlertTriangle className="stage-icon failed" />
          <span style={{ fontSize: '14px', color: 'var(--color-danger)' }}>{error}</span>
        </div>
      )}

      {loading && !results && (
        <div className="empty-state" style={{ padding: '60px' }}>
          <Loader2 className="stage-icon running" />
          <span>Loading optimization results...</span>
        </div>
      )}

      {results && (
        <>
          {/* Summary Grid */}
          <div className="summary-grid-3">
            <div className="card summary-card">
              <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                <Users />
              </div>
              <div className="card-info">
                <span className="card-label">Selected Members</span>
                <span className="card-value">{results.summary.total_selected}</span>
                <span className="card-subtext">Top-K Prioritized Patients</span>
              </div>
            </div>

            <div className="card summary-card">
              <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
                <AlertTriangle />
              </div>
              <div className="card-info">
                <span className="card-label">Total Gaps Addressed</span>
                <span className="card-value">{results.summary.total_gaps}</span>
                <span className="card-subtext">Targeted Clinical Gaps</span>
              </div>
            </div>

            <div className="card summary-card">
              <div className="card-icon-container" style={{ backgroundColor: 'var(--color-success-light)', color: 'var(--color-success)' }}>
                <Activity />
              </div>
              <div className="card-info">
                <span className="card-label">Avg Closure Probability</span>
                <span className="card-value">{(results.summary.avg_closure_probability != null ? results.summary.avg_closure_probability * 100 : 0).toFixed(1)}%</span>
                <span className="card-subtext">Estimated Likelihood</span>
              </div>
            </div>
          </div>

          <div className="card" style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Optimal Outreach List</h3>
                <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                  Displaying {results.records.length} prioritized patients addressing {results.summary.total_gaps} gaps.
                </p>
              </div>
            </div>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>S.No.</th>
                    <th>Member ID</th>
                    <th>Member Name</th>
                    <th>Age</th>
                    <th>Gender</th>
                    <th>Total Gaps</th>
                    <th>Care Gap(s) (Gap Name)</th>
                    <th>Recommended Intervention</th>
                    <th>Gap Status</th>
                    <th>Estimated Star Rating Improvement</th>
                  </tr>
                </thead>
                <tbody>
                  {results.records.map((rec) => (
                    <tr key={rec.s_no}>
                      <td>{rec.s_no}</td>
                      <td style={{ fontWeight: 600 }}>{rec.member_id}</td>
                      <td style={{ textTransform: 'capitalize' }}>{rec.member_name}</td>
                      <td>{rec.age}</td>
                      <td>{rec.gender}</td>
                      <td style={{ fontWeight: 700 }}>{rec.gap_count}</td>
                      <td>{rec.care_gaps}</td>
                      <td>
                        <span className="status-badge closed" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                          {rec.recommended_intervention}
                        </span>
                      </td>
                      <td>
                        <span className="status-badge open">
                          {rec.gap_status}
                        </span>
                      </td>
                      <td style={{ fontWeight: 700, color: 'var(--color-success)' }}>
                        {rec.contribution}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!results && !loading && !error && (
        <div className="card empty-state" style={{ padding: '60px', marginBottom: '24px' }}>
          <Activity className="empty-state-icon" />
          <h4 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-text-dark)', marginBottom: '8px' }}>No Optimization Results</h4>
          <p style={{ maxWidth: '400px', fontSize: '13px' }}>
            Run the pipeline by uploading a dataset to compute the optimal member outreach list.
          </p>
        </div>
      )}
    </div>
  );
};

// --- ERROR BOUNDARY ---
interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Metric Shift caught UI error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '400px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '40px',
          textAlign: 'center',
          gap: '16px'
        }}>
          <div className="card" style={{ maxWidth: '560px', padding: '32px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
            <AlertTriangle size={40} color="var(--color-danger)" style={{ marginBottom: '12px' }} />
            <h3 style={{ fontSize: '18px', fontWeight: 700, marginBottom: '8px' }}>Dashboard View Notice</h3>
            <p style={{ fontSize: '13px', color: 'var(--color-text-muted)', marginBottom: '20px' }}>
              {this.state.error?.message || 'An error occurred while loading this view.'}
            </p>
            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button
                className="btn btn-primary"
                onClick={() => {
                  this.setState({ hasError: false });
                  window.location.reload();
                }}
              >
                Reload Dashboard
              </button>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  localStorage.removeItem('ma_star_job_id');
                  window.location.href = '#/upload';
                  window.location.reload();
                }}
              >
                Reset & Upload New Data
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// --- MAIN ROUTER & APP ---
const AppContent: React.FC = () => {
  const [activeJobId, setActiveJobId] = useState<string>(getStoredJobId());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  const navigate = useNavigate();
  const location = useLocation();

  const handleUploadSuccess = (jobId: string) => {
    setActiveJobId(jobId);
    setStoredJobId(jobId);
  };

  // Restore latest run from backend if localStorage is empty
  useEffect(() => {
    const initRun = async () => {
      if (!activeJobId) {
        try {
          const latest = await getLatestRun();
          if (latest && latest.id) {
            setActiveJobId(latest.id);
            setStoredJobId(latest.id);
            setInitialLoading(false);
            return;
          }
        } catch (e) {
          // No previous runs found or API unreachable — go to upload
        }
        // No run available — ensure we land on upload
        setInitialLoading(false);
        navigate('/upload', { replace: true });
        return;
      }
      setInitialLoading(false);
    };
    initRun();
  }, []);

  // If no job ID has been loaded, enforce routing to /upload page
  useEffect(() => {
    if (!initialLoading && !activeJobId && location.pathname !== '/upload') {
      navigate('/upload', { replace: true });
    }
  }, [activeJobId, location.pathname, navigate, initialLoading]);

  // Show branded loading screen while restoring latest run
  if (initialLoading) {
    return (
      <div style={{
        width: '100vw',
        height: '100vh',
        background: 'var(--bg-primary)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: '20px'
      }}>
        <div style={{
          width: '64px',
          height: '64px',
          borderRadius: '14px',
          overflow: 'hidden',
          backgroundColor: '#09132c',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          boxShadow: '0 8px 32px rgba(30,82,232,0.18)'
        }}>
          <img
            src={logoImg}
            alt="Metric Shift"
            style={{ height: '100%', width: 'auto', objectFit: 'cover', objectPosition: 'left', transform: 'scale(1.4) translateX(2px)' }}
          />
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '22px', fontWeight: 800, color: 'var(--color-text-dark)', marginBottom: '4px' }}>Metric Shift</div>
          <div style={{ fontSize: '12px', color: 'var(--color-text-muted)' }}>Care Gap Detection & Star Rating Simulator</div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: 'var(--color-text-muted)', fontSize: '13px', marginTop: '8px' }}>
          <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
          <span>Loading workspace…</span>
        </div>
        <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div className="app-container">
      <NavigationSidebar activeJobId={activeJobId} collapsed={sidebarCollapsed} />

      <main className={`main-content ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <Routes>
          <Route
            path="/upload"
            element={
              <UploadPage
                onUploadSuccess={handleUploadSuccess}
                sidebarCollapsed={sidebarCollapsed}
                setSidebarCollapsed={setSidebarCollapsed}
              />
            }
          />
          <Route path="/pipeline/:jobId" element={<PipelinePage />} />

          {activeJobId ? (
            <>
              <Route
                path="/"
                element={
                  <HomeDashboard
                    jobId={activeJobId}
                    sidebarCollapsed={sidebarCollapsed}
                    setSidebarCollapsed={setSidebarCollapsed}
                  />
                }
              />
              <Route
                path="/optimization"
                element={
                  <OptimizationPage
                    jobId={activeJobId}
                    sidebarCollapsed={sidebarCollapsed}
                    setSidebarCollapsed={setSidebarCollapsed}
                  />
                }
              />
              <Route
                path="/plans"
                element={
                  <PlansPage
                    jobId={activeJobId}
                    sidebarCollapsed={sidebarCollapsed}
                    setSidebarCollapsed={setSidebarCollapsed}
                  />
                }
              />
              <Route
                path="/members"
                element={
                  <MembersPage
                    jobId={activeJobId}
                    sidebarCollapsed={sidebarCollapsed}
                    setSidebarCollapsed={setSidebarCollapsed}
                  />
                }
              />
              <Route
                path="/members/:memberId"
                element={
                  <MemberDetailsPage
                    jobId={activeJobId}
                    sidebarCollapsed={sidebarCollapsed}
                    setSidebarCollapsed={setSidebarCollapsed}
                  />
                }
              />
              <Route
                path="/cms-measures"
                element={
                  <CMSMeasuresPage
                    jobId={activeJobId}
                    sidebarCollapsed={sidebarCollapsed}
                    setSidebarCollapsed={setSidebarCollapsed}
                  />
                }
              />
            </>
          ) : (
            <Route path="*" element={<div className="empty-state"><UploadCloud size={28} /><span>Please upload a dataset to continue.</span><button className="btn btn-primary" onClick={() => navigate('/upload')}>Open Data & Updates</button></div>} />
          )}
        </Routes>
      </main>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <Router>
        <AppContent />
      </Router>
    </ErrorBoundary>
  );
};

export default App;
