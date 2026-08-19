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
  Menu,
  Star,
  TrendingUp
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
  listMembers,
  getMemberDetails,
  listMeasures,
  runOptimization,
  getDownloadUrl
} from './api/client';
import type {
  PipelineJob,
  DashboardMetrics,
  PlanDetails,
  MembersResponse,
  MemberDetails,
  CMSMeasuresResponse,
  OptimizationResponse
} from './api/client';
import logoImg from './assets/metric-shift-logo.png';

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
    { name: 'Dashboard', path: '/dashboard', icon: Home, disabled: !activeJobId },
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
  const [uploadMode, setUploadMode] = useState<'initial' | 'member_update'>('initial');
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
          <span className="eyebrow">DATA WORKFLOW</span>
          <h1>{isInitial ? 'Initialize the current database' : 'Update optimized members'}</h1>
          <p>
            {isInitial
              ? 'Load the complete 8-table workbook once to establish the live dataset and start the baseline pipeline.'
              : 'Upload updated records only for members selected by the latest optimization. Other members remain unchanged.'}
          </p>
        </div>
        <div className="workflow-step-count">
          <span>STEP</span>
          <strong>{isInitial ? '01' : '02'}</strong>
          <small>of 02</small>
        </div>
      </div>

      <div className="mode-grid">
        <button
          type="button"
          className={`mode-card ${isInitial ? 'selected' : ''}`}
          onClick={() => handleModeChange('initial')}
        >
          <div className="mode-card-icon"><FileSpreadsheet size={22} /></div>
          <div className="mode-card-copy">
            <span className="mode-card-kicker">START HERE</span>
            <h3>Initial Dataset</h3>
            <p>Complete 8-sheet workbook that seeds the current database.</p>
          </div>
          <span className="mode-card-radio">{isInitial ? '✓' : ''}</span>
        </button>

        <button
          type="button"
          className={`mode-card ${!isInitial ? 'selected' : ''}`}
          onClick={() => handleModeChange('member_update')}
        >
          <div className="mode-card-icon update"><Users size={22} /></div>
          <div className="mode-card-copy">
            <span className="mode-card-kicker">NEXT CYCLE</span>
            <h3>Member Update</h3>
            <p>Updated records for members selected by the latest optimization.</p>
          </div>
          <span className="mode-card-radio">{!isInitial ? '✓' : ''}</span>
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

    const checkStatus = async () => {
      try {
        const status = await getPipelineStatus(jobId);
        setJobState(status);

        if (status.status === 'completed') {
          setStoredJobId(jobId);
          const data = await getDashboardData(jobId);
          setMetrics(data);
        } else if (status.status === 'failed') {
          setError(status.error || 'Execution pipeline failed.');
        }
      } catch (err: any) {
        setError('Error fetching pipeline status.');
      }
    };

    checkStatus();
    const interval = setInterval(() => {
      if (jobState?.status !== 'completed' && jobState?.status !== 'failed') {
        checkStatus();
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [jobId, jobState?.status]);

  // 5 user-facing stages — each maps one or more internal backend stage keys.
  // The UI status is derived by checking all grouped internal keys:
  //   completed  → all grouped keys are completed
  //   failed     → any grouped key failed
  //   running    → any grouped key is running (and none failed)
  //   pending    → all grouped keys are still pending
  const uiStages: Array<{
    label: string;
    description: string;
    internalKeys: string[];
  }> = [
    {
      label: '1. File Upload',
      description: 'File uploaded and validated successfully.',
      internalKeys: ['file_upload'],
    },
    {
      label: '2. Rule Engine',
      description: 'Care-gap records are successfully identified.',
      internalKeys: ['rule_engine'],
    },
    {
      label: '3. ML Model Inference',
      description: 'ML predictions generated successfully.',
      // Groups: Candidate Generation, ML Model Inference, Logit-Space Channel Calibration
      internalKeys: ['candidate_generation', 'ml_inference', 'calibration'],
    },
    {
      label: '4. Optimization',
      description: 'Optimized successfully.',
      // Groups: Best Intervention Selection, MILP Optimization, Star Rating Contribution
      internalKeys: ['intervention_selection', 'milp_optimization', 'star_rating_contribution'],
    },
    {
      label: '5. Final Report',
      description: 'Final report generated successfully.',
      internalKeys: ['final_report'],
    },
  ];

  // Derives the aggregate status for a user-facing stage from its internal keys.
  const getGroupedStatus = (internalKeys: string[]): 'pending' | 'running' | 'completed' | 'failed' => {
    if (!jobState || !jobState.stages) return 'pending';
    const statuses = internalKeys.map((k) => jobState.stages?.[k]?.status || 'pending');
    if (statuses.some((s) => s === 'failed')) return 'failed';
    if (statuses.every((s) => s === 'completed')) return 'completed';
    if (statuses.some((s) => s === 'running' || s === 'completed')) return 'running';
    return 'pending';
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
        {uiStages.map((stage) => {
          const status = getGroupedStatus(stage.internalKeys);

          return (
            <div key={stage.label} className={`pipeline-stage ${status === 'running' ? 'running' : ''}`}>
              <div className={`stage-icon ${status}`}>
                {status === 'completed' && <CheckCircle size={16} />}
                {status === 'failed' && <AlertTriangle size={16} />}
                {status === 'running' && <Loader2 size={16} className="stage-icon running" />}
                {status === 'pending' && <span style={{ fontSize: '10px' }}>○</span>}
              </div>
              <div className="stage-info" style={{ flex: 1 }}>
                <span className="stage-name">{stage.label}</span>
                <span className="stage-message">{stage.description}</span>
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
            <div><strong>Total Active Plans:</strong> {metrics.summary.total_plans}</div>
            <div><strong>Total Members Processed:</strong> {metrics.summary.total_members.toLocaleString()}</div>
            <div><strong>Open Care Gaps:</strong> {metrics.summary.open_care_gaps.toLocaleString()}</div>
            <div><strong>CMS Quality Measures:</strong> {metrics.summary.cms_measures}</div>
          </div>
        </div>
      )}

      {jobState?.status === 'completed' && (
        <div style={{ marginTop: '32px', textAlign: 'center' }}>
          <button className="btn btn-primary" onClick={() => navigate('/')}>
            View Dashboard Results
          </button>
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
  const [planId, setPlanId] = useState('P001');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMetrics = async () => {
      setLoading(true);
      try {
        const data = await getDashboardData(jobId, planId);
        setMetrics(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchMetrics();
  }, [jobId, planId]);

  if (loading) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading analytics...</span></div>;
  }

  if (!metrics) {
    return <div className="empty-state">No dashboard analytics found.</div>;
  }

  return (
    <div>
      <NavigationHeader
        title="Home Dashboard"
        subtitle="Care Gap Detection & Star Rating Simulator"
        breadcrumbs={['Metric Shift']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text-dark)', margin: 0 }}>Clinical Performance Overview</h2>
      </div>

      <div className="summary-grid">
        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
            <FileSpreadsheet />
          </div>
          <div className="card-info">
            <span className="card-label">Total Plans</span>
            <span className="card-value">{metrics.summary.total_plans}</span>
            <span className="card-subtext">Medicare Advantage Plans</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-success-light)', color: 'var(--color-success)' }}>
            <Users />
          </div>
          <div className="card-info">
            <span className="card-label">Total Members</span>
            <span className="card-value">{metrics.summary.total_members.toLocaleString()}</span>
            <span className="card-subtext">Enrolled Members</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
            <AlertTriangle />
          </div>
          <div className="card-info">
            <span className="card-label">Open Care Gaps</span>
            <span className="card-value">{metrics.summary.open_care_gaps.toLocaleString()}</span>
            <span className="card-subtext">Care Gaps Identified</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-purple-light)', color: 'var(--color-purple)' }}>
            <CheckSquare />
          </div>
          <div className="card-info">
            <span className="card-label">CMS Measures</span>
            <span className="card-value">{metrics.summary.cms_measures}</span>
            <span className="card-subtext">Quality Measure Specifications</span>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-2">
        <div className="card">
          <h3 className="card-title">Care Gaps by Plan</h3>
          <div style={{ height: '300px' }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={metrics.gaps_by_plan}>
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
                {metrics.plan_performances.map((perf) => (
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
              <AreaChart data={metrics.improvement_trend}>
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
              {metrics.plan_performances.map((p) => (
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
            <button className="btn btn-secondary" style={{ width: '100%' }} onClick={() => setPlanId('P001')}>
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
  const [planId, setPlanId] = useState('P001');
  const [data, setData] = useState<PlanDetails | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
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

  if (loading) {
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
            style={{ width: '380px' }}
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
          >
            <option value="P001">P001 - Chronic Heart Failure &amp; Diabetes Mellitus Plan</option>
            <option value="P002">P002 - Cardiovascular Disorders &amp; Chronic Heart Failure Plan</option>
            <option value="P003">P003 - Cardiovascular Disorders &amp; Diabetes Mellitus Plan</option>
            <option value="P004">P004 - Complex CHF, Diabetes &amp; Cardiovascular Plan</option>
            <option value="P005">P005 - Cardiovascular Disorders &amp; Stroke Plan</option>
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
            <span className="card-value">{data.summary.total_members.toLocaleString()}</span>
            <span className="card-subtext">Enrolled Members</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
            <AlertTriangle />
          </div>
          <div className="card-info">
            <span className="card-label">Open Care Gaps</span>
            <span className="card-value">{data.summary.open_care_gaps.toLocaleString()}</span>
            <span className="card-subtext">Unresolved Gaps</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-purple-light)', color: 'var(--color-purple)' }}>
            <CheckSquare />
          </div>
          <div className="card-info">
            <span className="card-label">Care Gaps</span>
            <span className="card-value">{data.summary.total_care_gaps.toLocaleString()}</span>
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
              <span>{data.summary.plan_rating.toFixed(2)}</span>
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
          {data.resolved_over_time && data.resolved_over_time.length > 1 ? (
            <div style={{ height: '300px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data.resolved_over_time}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="year" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="resolved" fill="#1e52e8" radius={[4, 4, 0, 0]} label={{ position: 'top' }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="empty-state" style={{ height: '300px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <Activity className="empty-state-icon" size={32} style={{ opacity: 0.4, marginBottom: '8px' }} />
              <span style={{ fontSize: '13px', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                No historical resolution data available for this run.
              </span>
              <small style={{ color: 'var(--color-text-muted)', fontSize: '11px', marginTop: '4px' }}>
                Current Rating Year: {data.details.rating_year || 2026}
              </small>
            </div>
          )}
        </div>
      </div>

      <div className="dashboard-grid-2" style={{ marginBottom: '24px' }}>
        <div className="card">
          <h3 className="card-title">Star Rating Improvement Over Time</h3>
          {data.improvement_trend && data.improvement_trend.length > 1 ? (
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
          ) : (
            <div className="empty-state" style={{ height: '300px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
              <Activity className="empty-state-icon" size={32} style={{ opacity: 0.4, marginBottom: '8px' }} />
              <span style={{ fontSize: '13px', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                Historical star rating trend data is not available.
              </span>
              <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', fontWeight: 600 }}>Rating Year {data.details.rating_year || 2026}:</span>
                <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--color-success)' }}>{data.summary.plan_rating.toFixed(2)} ★</span>
              </div>
            </div>
          )}
        </div>

        <div className="card">
          <h3 className="card-title">Plan Details</h3>
          <div className="table-container" style={{ border: 'none', marginTop: 0 }}>
            <table className="data-table">
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan ID</td>
                  <td style={{ fontWeight: 700 }}>{data.details.plan_id}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan Name</td>
                  <td>{data.details.plan_name}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Contract ID</td>
                  <td>{data.details.contract_id}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan Type</td>
                  <td>{data.details.plan_type}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>County</td>
                  <td>{data.details.county}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Rating Year</td>
                  <td>{data.details.rating_year}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Start Date</td>
                  <td>{data.details.start_date}</td>
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
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [planId, setPlanId] = useState('');
  const [gender, setGender] = useState('');
  const [search, setSearch] = useState('');
  const [minAge, setMinAge] = useState('');
  const [maxAge, setMaxAge] = useState('');

  const loc = useLocation();

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
        min_age: minAge ? parseInt(minAge, 10) : undefined,
        max_age: maxAge ? parseInt(maxAge, 10) : undefined
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

      <div className="filter-panel">
        <div className="form-group">
          <label className="form-label">Search</label>
          <input
            type="text"
            className="form-input"
            placeholder="Name, Member ID, or Gap..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleApplyFilters()}
          />
        </div>

        <div className="form-group">
          <label className="form-label">Plan Filter</label>
          <select className="form-select" value={planId} onChange={(e) => setPlanId(e.target.value)}>
            <option value="">All Plans</option>
            <option value="P001">P001 - Chronic Heart Failure &amp; Diabetes Mellitus Plan</option>
            <option value="P002">P002 - Cardiovascular Disorders &amp; Chronic Heart Failure Plan</option>
            <option value="P003">P003 - Cardiovascular Disorders &amp; Diabetes Mellitus Plan</option>
            <option value="P004">P004 - Complex CHF, Diabetes &amp; Cardiovascular Plan</option>
            <option value="P005">P005 - Cardiovascular Disorders &amp; Stroke Plan</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Gender</label>
          <select className="form-select" value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="">All Genders</option>
            <option value="M">Male (M)</option>
            <option value="F">Female (F)</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">Age Range</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type="number"
              className="form-input"
              placeholder="Min"
              value={minAge}
              onChange={(e) => setMinAge(e.target.value)}
            />
            <input
              type="number"
              className="form-input"
              placeholder="Max"
              value={maxAge}
              onChange={(e) => setMaxAge(e.target.value)}
            />
          </div>
        </div>

        <div className="filter-actions">
          <button className="btn btn-primary" onClick={handleApplyFilters}>
            Filter
          </button>
          <button className="btn btn-secondary" onClick={handleClearFilters}>
            Clear
          </button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: '24px' }}>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Member ID</th>
                <th>Member Name</th>
                <th>DOB</th>
                <th>Age</th>
                <th>Gender</th>
                <th>Condition</th>
                <th>Plan ID</th>
                <th>Care Gaps</th>
                <th>Intervention</th>
                <th>Status</th>
                <th>Star Contribution</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {data && data.records.length > 0 ? (
                data.records.map((member) => (
                  <tr key={member.member_id}>
                    <td style={{ fontWeight: 600 }}>{member.member_id}</td>
                    <td style={{ textTransform: 'capitalize' }}>{member.member_name}</td>
                    <td>{member.dob}</td>
                    <td>{member.age}</td>
                    <td>{member.gender}</td>
                    <td>{member.condition}</td>
                    <td style={{ fontWeight: 600 }}>{member.plan_id}</td>
                    <td>{member.care_gaps || 'N/A'}</td>
                    <td>
                      <span className="status-badge closed" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                        {member.recommended_intervention || 'Standard'}
                      </span>
                    </td>
                    <td>
                      <span className="status-badge open">
                        {member.gap_status || 'Open'}
                      </span>
                    </td>
                    <td style={{ fontWeight: 700, color: 'var(--color-success)' }}>
                      {member.star_contribution || '0.0000'}
                    </td>
                    <td>
                      <Link to={`/members/${member.member_id}`} className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '12px' }}>
                        View Detail
                      </Link>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={12} style={{ textAlign: 'center', padding: '32px' }}>
                    No members match the selected criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {data && data.pagination.total_pages > 1 && (
          <div className="pagination">
            <button
              className="pagination-btn"
              disabled={page === 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={16} />
            </button>
            <span style={{ fontSize: '13px', color: 'var(--color-text-muted)' }}>
              Page {data.pagination.page} of {data.pagination.total_pages} ({data.pagination.total_records.toLocaleString()} members)
            </span>
            <button
              className="pagination-btn"
              disabled={page === data.pagination.total_pages}
              onClick={() => setPage((p) => Math.min(data.pagination.total_pages, p + 1))}
            >
              <ChevronRight size={16} />
            </button>
          </div>
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!memberId) return;

    const fetchDetail = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await getMemberDetails(jobId, memberId);
        setData(res);
      } catch (err: any) {
        setError('Member details could not be retrieved.');
      } finally {
        setLoading(false);
      }
    };
    fetchDetail();
  }, [jobId, memberId]);

  if (loading) {
    return <div className="empty-state"><Loader2 className="stage-icon running" /><span>Loading member profile...</span></div>;
  }

  if (error || !data) {
    return <div className="empty-state">{error || 'Member not found.'}</div>;
  }

  return (
    <div>
      <NavigationHeader
        title={`Member Details: ${data.member_name}`}
        subtitle={`Patient ID: ${data.member_id}`}
        breadcrumbs={['Home', 'Members', data.member_id]}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div className="summary-grid" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
            <Users />
          </div>
          <div className="card-info">
            <span className="card-label">Priority Level</span>
            <span className="card-value">{data.overall_priority}</span>
            <span className="card-subtext">Score: {data.priority_score.toFixed(1)}</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
            <AlertTriangle />
          </div>
          <div className="card-info">
            <span className="card-label">Open Care Gaps</span>
            <span className="card-value">{data.gaps_summary.open_care_gaps}</span>
            <span className="card-subtext">Pending Resolution</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-purple-light)', color: 'var(--color-purple)' }}>
            <Activity />
          </div>
          <div className="card-info">
            <span className="card-label">Channel</span>
            <span className="card-value">{data.recommended_intervention || 'None'}</span>
            <span className="card-subtext">Optimal Intervention</span>
          </div>
        </div>

        <div className="card summary-card">
          <div className="card-icon-container" style={{ backgroundColor: 'var(--color-success-light)', color: 'var(--color-success)' }}>
            <CheckSquare />
          </div>
          <div className="card-info">
            <span className="card-label">Star Contribution</span>
            <span className="card-value">{data.star_contribution || '0.0000'}</span>
            <span className="card-subtext">Potential Quality Lift</span>
          </div>
        </div>
      </div>

      <div className="dashboard-grid-2" style={{ marginBottom: '24px' }}>
        <div className="card">
          <h3 className="card-title">Demographics &amp; Health Plan</h3>
          <div className="table-container" style={{ border: 'none', marginTop: 0 }}>
            <table className="data-table">
              <tbody>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Full Name</td>
                  <td style={{ textTransform: 'capitalize' }}>{data.member_name}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Date of Birth / Age</td>
                  <td>{data.details.dob} ({data.details.age} yrs, {data.details.gender})</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Assigned Plan</td>
                  <td style={{ fontWeight: 600 }}>{data.details.health_plan}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Plan Type</td>
                  <td>{data.details.plan_type}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Clinical Condition</td>
                  <td>{data.details.conditions}</td>
                </tr>
                <tr>
                  <td style={{ fontWeight: 600, color: 'var(--color-text-muted)' }}>Enrollment Start Date</td>
                  <td>{data.details.enrollment_date}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h3 className="card-title">Care Gaps List</h3>
          <div className="table-container" style={{ border: 'none', marginTop: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Care Gap Name</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.care_gaps.map((gap, index) => (
                  <tr key={index}>
                    <td style={{ fontWeight: 600 }}>{gap.care_gap_name}</td>
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
  const [loading, setLoading] = useState(true);
  const [planId, setPlanId] = useState('P001');

  useEffect(() => {
    const fetchMeasures = async () => {
      setLoading(true);
      try {
        const res = await listMeasures(jobId, planId);
        setData(res);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchMeasures();
  }, [jobId, planId]);

  if (loading) {
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
            style={{ width: '380px' }}
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
          >
            <option value="P001">P001 - Chronic Heart Failure &amp; Diabetes Mellitus Plan</option>
            <option value="P002">P002 - Cardiovascular Disorders &amp; Chronic Heart Failure Plan</option>
            <option value="P003">P003 - Cardiovascular Disorders &amp; Diabetes Mellitus Plan</option>
            <option value="P004">P004 - Complex CHF, Diabetes &amp; Cardiovascular Plan</option>
            <option value="P005">P005 - Cardiovascular Disorders &amp; Stroke Plan</option>
          </select>
        </div>
      </div>

      <div className="summary-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
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
  const [planId, setPlanId] = useState('P001');
  const [maxMembers, setMaxMembers] = useState(15);
  const [totalPlanMembers, setTotalPlanMembers] = useState<number>(0);
  const [planLoading, setPlanLoading] = useState(false);
  const [results, setResults] = useState<OptimizationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Fetch total member count for the selected plan
  useEffect(() => {
    const fetchPlanTotalMembers = async () => {
      setPlanLoading(true);
      setResults(null);
      setValidationError(null);
      try {
        const planData = await getPlanData(jobId, planId);
        const count = planData.summary.total_members ?? 0;
        setTotalPlanMembers(count);
        // If current maxMembers exceeds the new plan's total, clamp it
        if (maxMembers > count && count > 0) {
          setMaxMembers(count);
        }
      } catch (err) {
        console.error('Failed to load plan members:', err);
        setTotalPlanMembers(0);
      } finally {
        setPlanLoading(false);
      }
    };
    fetchPlanTotalMembers();
  }, [jobId, planId]);

  const handleBudgetChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseInt(e.target.value, 10) || 1;
    setMaxMembers(val);
    if (totalPlanMembers > 0 && val > totalPlanMembers) {
      setValidationError(`Outreach limit cannot exceed the total members in this plan (${totalPlanMembers}).`);
    } else {
      setValidationError(null);
    }
  };

  const handleOptimize = async () => {
    if (validationError) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runOptimization(jobId, planId, maxMembers);
      setResults(res);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to execute outreach optimization. Try again.');
      setResults(null);
    } finally {
      setLoading(false);
    }
  };

  const isOptimizeDisabled = loading || planLoading || !!validationError || (totalPlanMembers > 0 && maxMembers > totalPlanMembers);

  return (
    <div>
      <NavigationHeader
        title="Outreach Optimization"
        subtitle="Solve optimal candidate selection using Mixed-Integer Linear Programming"
        breadcrumbs={['Home', 'Optimization']}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={setSidebarCollapsed}
      />

      <div className="filter-panel" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
        <div className="form-group">
          <label className="form-label">Select Plan</label>
          <select
            className="form-select"
            value={planId}
            onChange={(e) => setPlanId(e.target.value)}
          >
            <option value="P001">P001 - Chronic Heart Failure &amp; Diabetes Mellitus Plan</option>
            <option value="P002">P002 - Cardiovascular Disorders &amp; Chronic Heart Failure Plan</option>
            <option value="P003">P003 - Cardiovascular Disorders &amp; Diabetes Mellitus Plan</option>
            <option value="P004">P004 - Complex CHF, Diabetes &amp; Cardiovascular Plan</option>
            <option value="P005">P005 - Cardiovascular Disorders &amp; Stroke Plan</option>
          </select>
        </div>

        <div className="form-group">
          <label className="form-label">
            Member Outreach Budget Limit
            {totalPlanMembers > 0 && (
              <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '8px' }}>
                {maxMembers} / {totalPlanMembers} Total Members
              </span>
            )}
            {planLoading && (
              <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', marginLeft: '8px', fontSize: '12px' }}>
                Loading...
              </span>
            )}
          </label>
          <input
            type="number"
            className="form-input"
            style={validationError ? { borderColor: 'var(--color-danger)' } : {}}
            value={maxMembers}
            min={1}
            max={totalPlanMembers > 0 ? totalPlanMembers : undefined}
            onChange={handleBudgetChange}
          />
          {validationError && (
            <span style={{ fontSize: '12px', color: 'var(--color-danger)', marginTop: '4px', display: 'block' }}>
              {validationError}
            </span>
          )}
        </div>

        <div className="filter-actions" style={{ width: '100%' }}>
          <button
            className="btn btn-primary"
            style={{ width: '100%', height: '42px' }}
            onClick={handleOptimize}
            disabled={isOptimizeDisabled}
          >
            {loading ? (
              <>
                <Loader2 size={16} className="stage-icon running" />
                <span>Solving MILP...</span>
              </>
            ) : (
              <span>OPTIMIZE</span>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="pipeline-stage failed" style={{ marginBottom: '24px', gap: '12px' }}>
          <AlertTriangle className="stage-icon failed" />
          <span style={{ fontSize: '14px', color: 'var(--color-danger)' }}>{error}</span>
        </div>
      )}

      {results && (
        <>
          {/* Summary Banner */}
          <div className="pipeline-stage completed" style={{ marginBottom: '24px', gap: '12px', padding: '12px 20px' }}>
            <CheckSquare className="stage-icon completed" />
            <span style={{ fontSize: '14px', fontWeight: 600 }}>
              Selected {results.summary.total_selected} patients addressing {results.summary.total_gaps} gaps.
            </span>
          </div>

          {/* Star Rating Cards */}
          {(results.summary.prev_plan_rating ?? 0) > 0 && (
            <div className="summary-grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)', marginBottom: '24px' }}>
              <div className="card summary-card">
                <div className="card-icon-container" style={{ backgroundColor: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                  <Activity />
                </div>
                <div className="card-info">
                  <span className="card-label">Previous Plan Rating</span>
                  <div className="card-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>{results.summary.prev_plan_rating?.toFixed(2)}</span>
                    <StarRating rating={results.summary.prev_plan_rating ?? 0} />
                  </div>
                  <span className="card-subtext">Current CMS Star Rating</span>
                </div>
              </div>

              <div className="card summary-card">
                <div className="card-icon-container" style={{ backgroundColor: 'var(--color-success-light)', color: 'var(--color-success)' }}>
                  <TrendingUp />
                </div>
                <div className="card-info">
                  <span className="card-label">Projected Star Rating</span>
                  <div className="card-value" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>{results.summary.projected_plan_rating?.toFixed(2)}</span>
                    <StarRating rating={results.summary.projected_plan_rating ?? 0} />
                  </div>
                  <span className="card-subtext">After Outreach Campaign</span>
                </div>
              </div>

              <div className="card summary-card">
                <div className="card-icon-container" style={{ backgroundColor: 'var(--color-warning-light)', color: 'var(--color-warning)' }}>
                  <Star />
                </div>
                <div className="card-info">
                  <span className="card-label">Star Rating Increase</span>
                  <span className="card-value" style={{ color: 'var(--color-success)' }}>
                    +{results.summary.star_increase?.toFixed(2)}
                  </span>
                  <span className="card-subtext">Projected Improvement</span>
                </div>
              </div>
            </div>
          )}

          {/* Optimal Outreach List */}
          <div className="card" style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 700 }}>Optimal Outreach List</h3>
                <p style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                  Selected {results.summary.total_selected} patients addressing {results.summary.total_gaps} gaps.
                </p>
              </div>
              <a
                href={getDownloadUrl(jobId, planId, maxMembers)}
                className="btn btn-secondary"
                style={{ display: 'flex', alignItems: 'center', gap: '8px', textDecoration: 'none' }}
              >
                <Download size={16} />
                <span>Download Final Member Report (.xlsx)</span>
              </a>
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

      {!results && !loading && (
        <div className="card empty-state" style={{ padding: '60px', marginBottom: '24px' }}>
          <Activity className="empty-state-icon" />
          <h4 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--color-text-dark)', marginBottom: '8px' }}>Optimization Results Empty</h4>
          <p style={{ maxWidth: '400px', fontSize: '13px' }}>
            Choose a plan and click the Optimize button to run the backend linear solver and select candidate outreaches.
          </p>
        </div>
      )}
    </div>
  );
};

// --- LANDING PAGE ---
const LandingPage: React.FC = () => {
  const navigate = useNavigate();

  const goToDashboard = () => navigate('/dashboard');

  return (
    <div className="metric-shift-landing">
      <style>{`
        .metric-shift-landing {
          --lp-navy: #0B3B3A;
          --lp-teal: #0F7173;
          --lp-teal2: #17898A;
          --lp-teal-light: #EAF6F4;
          --lp-bg: #F7FBFA;
          --lp-white: #fff;
          --lp-muted: #6B7D7B;
          --lp-line: #DDE8E6;
          --lp-orange: #E39B2F;
          --lp-green: #25A879;
          --lp-red: #D85D5D;
          --lp-shadow: 0 12px 30px rgba(11,59,58,.08);

          font-family: Inter, Arial, sans-serif;
          background: var(--lp-bg);
          color: var(--lp-navy);
          line-height: 1.5;
          min-height: 100vh;
          width: 100%;
          box-sizing: border-box;
          overflow-x: hidden;
        }

        .metric-shift-landing * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }

        .metric-shift-landing .wrap {
          width: 100%;
          max-width: 1180px;
          margin-left: auto;
          margin-right: auto;
          padding-left: clamp(16px, 3.5vw, 28px);
          padding-right: clamp(16px, 3.5vw, 28px);
          box-sizing: border-box;
        }

        /* NAV */
        .metric-shift-landing .nav {
          min-height: 76px;
          height: auto;
          padding: 12px 0;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 12px 20px;
        }
        .metric-shift-landing .logo {
          display: flex;
          align-items: center;
          gap: 10px;
          background: none;
          border: none;
          padding: 0;
          cursor: pointer;
          text-decoration: none;
          flex-shrink: 0;
        }
        .metric-shift-landing .logo-img {
          height: clamp(32px, 4vw, 42px);
          width: auto;
          max-width: 100%;
          object-fit: contain;
          display: block;
        }
        .metric-shift-landing .menu {
          display: flex;
          gap: clamp(14px, 2.5vw, 30px);
          font-size: clamp(12px, 1.4vw, 13px);
          font-weight: 600;
          color: #294B49;
          align-items: center;
        }
        .metric-shift-landing .menu a {
          text-decoration: none;
          color: inherit;
          transition: color 0.15s;
          white-space: nowrap;
        }
        .metric-shift-landing .menu a:hover {
          color: var(--lp-teal);
        }
        .metric-shift-landing .nav-btn {
          background: var(--lp-teal);
          color: #fff;
          padding: clamp(9px, 1.5vw, 11px) clamp(14px, 2vw, 18px);
          border-radius: 9px;
          font-size: clamp(12px, 1.4vw, 13px);
          font-weight: 700;
          border: none;
          cursor: pointer;
          text-decoration: none;
          display: inline-flex;
          align-items: center;
          transition: background 0.15s;
          white-space: nowrap;
          flex-shrink: 0;
        }
        .metric-shift-landing .nav-btn:hover {
          background: var(--lp-teal2);
        }

        /* HERO */
        .metric-shift-landing .hero {
          padding: clamp(28px, 4.5vw, 48px) 0 clamp(40px, 6vw, 70px);
        }
        .metric-shift-landing .hero-grid {
          display: grid;
          grid-template-columns: minmax(0, 1.12fr) minmax(0, 0.88fr);
          gap: clamp(28px, 4.5vw, 65px);
          align-items: center;
        }
        .metric-shift-landing .eyebrow {
          text-transform: uppercase;
          letter-spacing: .08em;
          font-size: clamp(10px, 1.2vw, 11px);
          font-weight: 800;
          color: var(--lp-teal);
          margin-bottom: 10px;
        }
        .metric-shift-landing h1 {
          font-size: clamp(30px, 4.2vw, 48px);
          line-height: 1.08;
          letter-spacing: -.035em;
          margin-bottom: clamp(14px, 2vw, 20px);
          color: var(--lp-navy);
          font-weight: 800;
          word-break: break-word;
          overflow-wrap: break-word;
        }
        .metric-shift-landing h1 span {
          color: var(--lp-teal);
        }
        .metric-shift-landing .hero-text {
          max-width: 520px;
          color: var(--lp-muted);
          font-size: clamp(13.5px, 1.5vw, 15px);
          line-height: 1.7;
          margin-bottom: clamp(18px, 2.5vw, 28px);
        }
        .metric-shift-landing .actions {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
        }
        .metric-shift-landing .btn {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: clamp(10px, 1.6vw, 13px) clamp(16px, 2.2vw, 22px);
          border-radius: 9px;
          font-size: clamp(12px, 1.4vw, 13px);
          font-weight: 700;
          text-decoration: none;
          cursor: pointer;
          border: none;
          transition: all 0.15s;
          white-space: nowrap;
        }
        .metric-shift-landing .btn.primary {
          background: var(--lp-teal);
          color: #fff;
        }
        .metric-shift-landing .btn.primary:hover {
          background: var(--lp-teal2);
        }
        .metric-shift-landing .btn.secondary {
          border: 1px solid var(--lp-teal);
          color: var(--lp-teal);
          background: transparent;
        }
        .metric-shift-landing .btn.secondary:hover {
          background: var(--lp-teal-light);
        }
        .metric-shift-landing .stats {
          display: flex;
          gap: clamp(16px, 3.5vw, 35px);
          margin-top: clamp(24px, 4vw, 42px);
          flex-wrap: wrap;
        }
        .metric-shift-landing .stat strong {
          font-size: clamp(20px, 2.8vw, 25px);
          color: var(--lp-orange);
          display: block;
          font-weight: 800;
        }
        .metric-shift-landing .stat small {
          font-size: clamp(10.5px, 1.2vw, 11px);
          color: var(--lp-muted);
        }

        /* DASHBOARD PREVIEW */
        .metric-shift-landing .preview {
          background: #fff;
          border-radius: clamp(16px, 2.5vw, 22px);
          padding: clamp(14px, 2vw, 18px);
          box-shadow: 0 22px 55px rgba(11,59,58,.14);
          border: 1px solid #edf3f2;
          width: 100%;
          max-width: 520px;
          margin: 0 auto;
          box-sizing: border-box;
        }
        .metric-shift-landing .preview-top {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: clamp(10px, 1.5vw, 15px);
          gap: 8px;
        }
        .metric-shift-landing .preview-title {
          font-size: clamp(11px, 1.4vw, 12px);
          font-weight: 800;
          color: var(--lp-navy);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .metric-shift-landing .badge {
          background: #EAF8F1;
          color: var(--lp-green);
          padding: 4px 8px;
          border-radius: 6px;
          font-size: 9px;
          font-weight: 800;
          letter-spacing: 0.05em;
          flex-shrink: 0;
        }
        .metric-shift-landing .kpis {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: clamp(5px, 1vw, 8px);
        }
        .metric-shift-landing .kpi {
          background: #F6FAF9;
          border-radius: 10px;
          padding: clamp(8px, 1.3vw, 12px);
          min-width: 0;
          overflow: hidden;
        }
        .metric-shift-landing .kpi label {
          font-size: clamp(7.5px, 0.9vw, 8px);
          text-transform: uppercase;
          color: var(--lp-muted);
          font-weight: 700;
          display: block;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .metric-shift-landing .kpi strong {
          display: block;
          font-size: clamp(14px, 2vw, 18px);
          margin-top: 3px;
          color: var(--lp-navy);
          font-weight: 800;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .metric-shift-landing .kpi .up {
          color: var(--lp-green);
        }
        .metric-shift-landing .chart {
          height: clamp(95px, 14vw, 130px);
          margin-top: 10px;
          background: #F6FAF9;
          border-radius: 11px;
          padding: clamp(8px, 1.4vw, 14px);
          display: flex;
          align-items: flex-end;
          gap: clamp(4px, 1vw, 8px);
        }
        .metric-shift-landing .bar {
          flex: 1;
          background: linear-gradient(to top, var(--lp-teal), #65C9C3);
          border-radius: 4px 4px 0 0;
          min-width: 4px;
        }
        .metric-shift-landing .preview-row {
          display: flex;
          gap: 8px;
          margin-top: 10px;
          flex-wrap: wrap;
        }
        .metric-shift-landing .mini-card {
          flex: 1 1 130px;
          background: #F6FAF9;
          border-radius: 10px;
          padding: clamp(8px, 1.2vw, 10px);
          font-size: 9px;
          color: var(--lp-navy);
          min-width: 0;
        }
        .metric-shift-landing .mini-card b {
          display: block;
          font-size: clamp(10px, 1.3vw, 11px);
          margin-bottom: 4px;
          color: var(--lp-navy);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .metric-shift-landing .progress {
          height: 5px;
          background: #DCE8E6;
          border-radius: 5px;
          overflow: hidden;
          margin-top: 5px;
        }
        .metric-shift-landing .progress i {
          display: block;
          height: 100%;
          background: var(--lp-teal);
          border-radius: 5px;
          font-style: normal;
        }

        /* FEATURES */
        .metric-shift-landing .section {
          padding: clamp(40px, 6vw, 72px) 0;
        }
        .metric-shift-landing .section-head {
          text-align: center;
          max-width: 650px;
          margin: 0 auto clamp(24px, 4vw, 38px);
          padding: 0 10px;
        }
        .metric-shift-landing .section-head h2 {
          font-size: clamp(22px, 3.2vw, 29px);
          letter-spacing: -.02em;
          margin-bottom: 10px;
          color: var(--lp-navy);
          font-weight: 800;
          line-height: 1.2;
        }
        .metric-shift-landing .section-head p {
          font-size: clamp(13px, 1.5vw, 14px);
          color: var(--lp-muted);
          line-height: 1.6;
        }
        .metric-shift-landing .features {
          display: grid;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          gap: clamp(10px, 1.5vw, 15px);
        }
        .metric-shift-landing .feature-card {
          background: #fff;
          border: 1px solid var(--lp-line);
          border-radius: clamp(14px, 2vw, 17px);
          padding: clamp(16px, 2.2vw, 24px) clamp(12px, 1.8vw, 18px);
          box-shadow: var(--lp-shadow);
          min-width: 0;
          display: flex;
          flex-direction: column;
        }
        .metric-shift-landing .feature-card .icon {
          width: 42px;
          height: 42px;
          border-radius: 11px;
          background: var(--lp-teal-light);
          color: var(--lp-teal);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 19px;
          margin-bottom: clamp(12px, 1.8vw, 17px);
          flex-shrink: 0;
        }
        .metric-shift-landing .feature-card h3 {
          font-size: clamp(13px, 1.5vw, 14px);
          margin-bottom: 8px;
          color: var(--lp-navy);
          font-weight: 700;
          line-height: 1.3;
        }
        .metric-shift-landing .feature-card p {
          font-size: clamp(11px, 1.3vw, 11.5px);
          color: var(--lp-muted);
          line-height: 1.6;
        }

        /* FLOW / WORKFLOW */
        .metric-shift-landing .flow-section {
          background: #fff;
          border-radius: clamp(18px, 3vw, 26px);
          padding: clamp(24px, 4.5vw, 55px);
          border: 1px solid var(--lp-line);
          box-sizing: border-box;
        }
        .metric-shift-landing .flow {
          display: grid;
          grid-template-columns: repeat(5, minmax(0, 1fr));
          gap: 0;
          margin-top: clamp(20px, 3.5vw, 35px);
        }
        .metric-shift-landing .step {
          text-align: center;
          position: relative;
          padding: 0 clamp(6px, 1.2vw, 12px);
          min-width: 0;
        }
        .metric-shift-landing .step:not(:last-child):after {
          content: "→";
          position: absolute;
          right: -9px;
          top: 11px;
          color: #A7BFBC;
          font-size: clamp(14px, 1.8vw, 18px);
        }
        .metric-shift-landing .step-num {
          width: clamp(32px, 4vw, 38px);
          height: clamp(32px, 4vw, 38px);
          border-radius: 50%;
          background: var(--lp-teal);
          color: #fff;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          font-size: clamp(11px, 1.4vw, 12px);
          margin: 0 auto 12px;
        }
        .metric-shift-landing .step h3 {
          font-size: clamp(12px, 1.4vw, 13px);
          margin-bottom: 5px;
          color: var(--lp-navy);
          font-weight: 700;
        }
        .metric-shift-landing .step p {
          font-size: clamp(10px, 1.2vw, 10.5px);
          color: var(--lp-muted);
          line-height: 1.5;
        }

        /* AUDIENCE / BUILT FOR */
        .metric-shift-landing .audience {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: clamp(12px, 2vw, 18px);
        }
        .metric-shift-landing .aud {
          background: #fff;
          border-radius: clamp(12px, 2vw, 15px);
          padding: clamp(16px, 2.5vw, 24px);
          border: 1px solid var(--lp-line);
          min-width: 0;
        }
        .metric-shift-landing .aud .icon {
          width: 42px;
          height: 42px;
          border-radius: 11px;
          background: var(--lp-teal-light);
          color: var(--lp-teal);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 19px;
          margin-bottom: 12px;
        }
        .metric-shift-landing .aud h3 {
          font-size: clamp(13px, 1.5vw, 14px);
          margin: 0 0 5px;
          color: var(--lp-navy);
          font-weight: 700;
        }
        .metric-shift-landing .aud p {
          font-size: clamp(11.5px, 1.3vw, 12px);
          color: var(--lp-muted);
          line-height: 1.6;
        }

        /* CTA */
        .metric-shift-landing .cta {
          background: var(--lp-teal);
          color: #fff;
          border-radius: clamp(16px, 2.5vw, 22px);
          padding: clamp(24px, 4vw, 42px);
          display: flex;
          justify-content: space-between;
          align-items: center;
          gap: 20px;
          margin-bottom: clamp(28px, 4vw, 45px);
          flex-wrap: wrap;
        }
        .metric-shift-landing .cta-content {
          flex: 1 1 280px;
          min-width: 0;
        }
        .metric-shift-landing .cta .eyebrow {
          color: #BFE7DF;
          margin: 0;
        }
        .metric-shift-landing .cta h2 {
          font-size: clamp(20px, 3vw, 25px);
          margin-top: 4px;
          color: #fff;
          font-weight: 800;
          line-height: 1.2;
        }
        .metric-shift-landing .cta p {
          font-size: clamp(11px, 1.3vw, 12px);
          color: #C6E6E1;
          margin-top: 5px;
        }
        .metric-shift-landing .cta .btn.primary {
          background: #fff;
          color: var(--lp-navy);
          white-space: nowrap;
          flex-shrink: 0;
        }
        .metric-shift-landing .cta .btn.primary:hover {
          background: #EAF6F4;
        }

        /* FOOTER */
        .metric-shift-landing footer {
          padding: clamp(20px, 3vw, 28px) 0 clamp(28px, 4vw, 40px);
          border-top: 1px solid var(--lp-line);
          font-size: clamp(10px, 1.2vw, 11px);
          color: var(--lp-muted);
          display: flex;
          justify-content: space-between;
          align-items: center;
          flex-wrap: wrap;
          gap: 10px;
        }

        /* RESPONSIVE MEDIA QUERIES */
        @media(max-width: 1024px) {
          .metric-shift-landing .features {
            grid-template-columns: repeat(3, minmax(0, 1fr));
          }
        }

        @media(max-width: 950px) {
          .metric-shift-landing .hero-grid {
            grid-template-columns: 1fr;
            gap: 36px;
          }
          .metric-shift-landing .hero-text {
            max-width: 100%;
          }
          .metric-shift-landing .preview {
            max-width: 480px;
          }
          .metric-shift-landing .flow {
            grid-template-columns: 1fr;
            gap: 22px;
          }
          .metric-shift-landing .step:not(:last-child):after {
            content: "↓";
            right: 50%;
            top: auto;
            bottom: -18px;
            transform: translateX(50%);
          }
          .metric-shift-landing .flow-section {
            padding: clamp(24px, 4vw, 35px) clamp(16px, 3vw, 20px);
          }
        }

        @media(max-width: 768px) {
          .metric-shift-landing .features {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .metric-shift-landing .audience {
            grid-template-columns: 1fr;
          }
        }

        @media(max-width: 600px) {
          .metric-shift-landing .nav {
            justify-content: space-between;
          }
          .metric-shift-landing .menu {
            order: 3;
            width: 100%;
            justify-content: center;
            padding-top: 8px;
            border-top: 1px solid rgba(221, 232, 230, 0.6);
          }
          .metric-shift-landing .stats {
            gap: 16px 24px;
          }
          .metric-shift-landing .cta {
            flex-direction: column;
            align-items: flex-start;
          }
          .metric-shift-landing .cta .btn.primary {
            width: 100%;
          }
          .metric-shift-landing footer {
            flex-direction: column;
            align-items: center;
            text-align: center;
          }
        }

        @media(max-width: 440px) {
          .metric-shift-landing .features {
            grid-template-columns: 1fr;
          }
          .metric-shift-landing .actions {
            flex-direction: column;
          }
          .metric-shift-landing .actions .btn {
            width: 100%;
          }
        }
      `}</style>

      {/* NAV */}
      <header className="wrap nav">
        <button
          className="logo"
          onClick={() => navigate('/')}
          aria-label="Metric Shift Home"
        >
          <img
            src={logoImg}
            alt="Metric Shift"
            className="logo-img"
          />
        </button>
        <nav className="menu">
          <a href="#features">Features</a>
          <a href="#workflow">Workflow</a>
          <a href="#audience">Who it's for</a>
        </nav>
        <button className="nav-btn" onClick={goToDashboard}>
          Open Dashboard →
        </button>
      </header>

      <main>
        {/* HERO */}
        <section className="wrap hero">
          <div className="hero-grid">
            <div>
              <div className="eyebrow">Medicare Advantage Quality Intelligence</div>
              <h1>Turn care gaps into <span>measurable impact.</span></h1>
              <p className="hero-text">
                Metric Shift brings star-rating tracking, care-gap prioritization,
                intervention optimization, and impact simulation into one quality command center.
              </p>
              <div className="actions">
                <button className="btn primary" onClick={goToDashboard}>
                  Open the Dashboard
                </button>
                <a className="btn secondary" href="#features">
                  Explore Features
                </a>
              </div>
              <div className="stats">
                <div className="stat"><strong>Live</strong><small>Quality monitoring</small></div>
                <div className="stat"><strong>5</strong><small>Total Plans</small></div>
                <div className="stat"><strong>360°</strong><small>Member &amp; measure view</small></div>
              </div>
            </div>

            <div className="preview">
              <div className="preview-top">
                <div className="preview-title">Metric Shift · Quality Command Center</div>
                <div className="badge">● LIVE</div>
              </div>
              <div className="kpis">
                <div className="kpi"><label>Current Rating</label><strong>3.5 ★</strong></div>
                <div className="kpi"><label>Projected</label><strong className="up">4.0 ★</strong></div>
                <div className="kpi"><label>Priority Gaps</label><strong>248</strong></div>
              </div>
              <div className="chart">
                <div className="bar" style={{ height: '38%' }} />
                <div className="bar" style={{ height: '55%' }} />
                <div className="bar" style={{ height: '48%' }} />
                <div className="bar" style={{ height: '73%' }} />
                <div className="bar" style={{ height: '61%' }} />
                <div className="bar" style={{ height: '84%' }} />
                <div className="bar" style={{ height: '76%' }} />
              </div>
              <div className="preview-row">
                <div className="mini-card">
                  <b>Care-gap closure</b>82%
                  <div className="progress"><i style={{ width: '82%' }} /></div>
                </div>
                <div className="mini-card">
                  <b>Optimization impact</b>+0.5 ★
                  <div className="progress"><i style={{ width: '76%' }} /></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* FEATURES */}
        <section className="wrap section" id="features">
          <div className="section-head">
            <div className="eyebrow">Core Features</div>
            <h2>Everything needed to shift the metric</h2>
            <p>From finding the right members to predicting the quality impact, Metric Shift keeps the complete decision flow in one place.</p>
          </div>

          <div className="features">
            <article className="feature-card">
              <div className="icon">📊</div>
              <h3>Star Rating Tracking</h3>
              <p>Monitor measure performance and understand how close each measure is to the next star cut point.</p>
            </article>
            <article className="feature-card">
              <div className="icon">🎯</div>
              <h3>Care Gap Prioritization</h3>
              <p>Find open gaps and prioritize members based on where intervention can create the greatest value.</p>
            </article>
            <article className="feature-card">
              <div className="icon">⚡</div>
              <h3>Intervention Optimization</h3>
              <p>Select measures, capacity, and expected closure rates to identify an effective intervention strategy.</p>
            </article>
            <article className="feature-card">
              <div className="icon">📈</div>
              <h3>Impact Simulation</h3>
              <p>Run what-if scenarios and compare current versus projected star-rating outcomes before acting.</p>
            </article>
            <article className="feature-card">
              <div className="icon">👥</div>
              <h3>Member Insights</h3>
              <p>Drill into individual members, care gaps, conditions, outreach information, and intervention history.</p>
            </article>
          </div>
        </section>

        {/* WORKFLOW */}
        <section className="wrap section" id="workflow">
          <div className="flow-section">
            <div className="section-head">
              <div className="eyebrow">How Metric Shift Works</div>
              <h2>From data to quality improvement</h2>
              <p>A simple workflow that connects measurement, prioritization, optimization, and action.</p>
            </div>
            <div className="flow">
              <div className="step">
                <div className="step-num">01</div>
                <h3>Track</h3>
                <p>Monitor star measures and current performance.</p>
              </div>
              <div className="step">
                <div className="step-num">02</div>
                <h3>Identify</h3>
                <p>Find members with actionable care gaps.</p>
              </div>
              <div className="step">
                <div className="step-num">03</div>
                <h3>Prioritize</h3>
                <p>Rank gaps by potential quality impact.</p>
              </div>
              <div className="step">
                <div className="step-num">04</div>
                <h3>Optimize</h3>
                <p>Select the best intervention strategy.</p>
              </div>
              <div className="step">
                <div className="step-num">05</div>
                <h3>Simulate</h3>
                <p>Project the star-rating shift before outreach.</p>
              </div>
            </div>
          </div>
        </section>

        {/* AUDIENCE */}
        <section className="wrap section" id="audience">
          <div className="section-head">
            <div className="eyebrow">Built For</div>
            <h2>Teams closest to the quality score</h2>
          </div>
          <div className="audience">
            <div className="aud">
              <div className="icon">📋</div>
              <h3>Program Analysts</h3>
              <p>Monitor measures, contracts, performance, and cut-point proximity.</p>
            </div>
            <div className="aud">
              <div className="icon">🩺</div>
              <h3>Care Management</h3>
              <p>Prioritize members and focus outreach on the gaps that matter most.</p>
            </div>
            <div className="aud">
              <div className="icon">📊</div>
              <h3>Quality &amp; Analytics</h3>
              <p>Model scenarios, evaluate outcomes, and connect interventions to quality improvement.</p>
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="wrap">
          <div className="cta">
            <div className="cta-content">
              <div className="eyebrow">Ready to move the metric?</div>
              <h2>See where your star rating can shift.</h2>
              <p>Open the command center and explore the full Metric Shift workflow.</p>
            </div>
            <button className="btn primary" onClick={goToDashboard}>
              Open Dashboard →
            </button>
          </div>
        </section>
      </main>

      <footer className="wrap">
        <span>© 2026 Metric Shift · Medicare Advantage Quality Intelligence</span>
        <span>Track · Prioritize · Optimize · Simulate</span>
      </footer>
    </div>
  );
};

// --- MAIN ROUTER & APP ---
const AppContent: React.FC = () => {
  const [activeJobId, setActiveJobId] = useState<string>(getStoredJobId());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();

  const handleUploadSuccess = (jobId: string) => {
    setActiveJobId(jobId);
    setStoredJobId(jobId);
  };

  useEffect(() => {
    // Allow landing page (/) and upload page without a jobId.
    // All other app routes require an active job.
    if (!activeJobId && location.pathname !== '/upload' && location.pathname !== '/') {
      navigate('/upload', { replace: true });
    }
  }, [activeJobId, location.pathname, navigate]);

  // The landing page renders full-width with no sidebar chrome.
  const isLandingPage = location.pathname === '/';

  if (isLandingPage) {
    return (
      <Routes>
        <Route path="/" element={<LandingPage />} />
      </Routes>
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
                path="/dashboard"
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
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <UploadCloud size={28} />
                  <span>Please upload a dataset to continue.</span>
                  <button className="btn btn-primary" onClick={() => navigate('/upload')}>
                    Open Data & Updates
                  </button>
                </div>
              }
            />
          )}
        </Routes>
      </main>
    </div>
  );
};

const App: React.FC = () => {
  return (
    <Router>
      <AppContent />
    </Router>
  );
};

export default App;
