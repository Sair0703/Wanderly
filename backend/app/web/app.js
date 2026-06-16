const { useState, useEffect, useCallback, useRef } = React;

/* ----------------------------- API client ----------------------------- */
const TOKEN_KEY = "wanderly_token";
const api = {
  token: () => localStorage.getItem(TOKEN_KEY),
  setToken: (t) => t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY),
  async call(path, { method = "GET", body } = {}) {
    const headers = { "Content-Type": "application/json" };
    const t = api.token();
    if (t) headers["Authorization"] = `Bearer ${t}`;
    const res = await fetch(`/api${path}`, {
      method, headers, body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (e) {}
      throw new Error(detail);
    }
    return res.status === 204 ? null : res.json();
  },
};

/* ----------------------------- Helpers ----------------------------- */
const money = (n) => "$" + Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 });
const ALL_TAGS = ["beach","city","food","history","nature","adventure","nightlife","art","relax","mountain","ski","tropical","wine","desert"];
const bookingSite = (url) => {
  if (!url) return "partner site";
  if (url.includes("booking.com")) return "Booking.com";
  if (url.includes("google.com")) return "Google Hotels";
  if (url.includes("expedia")) return "Expedia";
  return "partner site";
};

function useToast() {
  const [msg, setMsg] = useState(null);
  const show = useCallback((m) => { setMsg(m); setTimeout(() => setMsg(null), 2600); }, []);
  const node = msg ? <div className="toast">{msg}</div> : null;
  return [node, show];
}

/* ----------------------------- Map ----------------------------- */
function MiniMap({ listings, height = 240 }) {
  const ref = useRef(null);
  const mapRef = useRef(null);
  useEffect(() => {
    if (!ref.current || !window.L) return;
    const pts = listings.filter((l) => l.lat || l.lng);
    if (!mapRef.current) {
      mapRef.current = L.map(ref.current, { scrollWheelZoom: false });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap", maxZoom: 18,
      }).addTo(mapRef.current);
    }
    const map = mapRef.current;
    map._markers && map._markers.forEach((m) => map.removeLayer(m));
    map._markers = pts.map((l) =>
      L.marker([l.lat, l.lng]).addTo(map).bindPopup(`<b>${l.title}</b><br/>${money(l.price_per_night)}/night`)
    );
    if (pts.length === 1) map.setView([pts[0].lat, pts[0].lng], 11);
    else if (pts.length > 1) map.fitBounds(pts.map((l) => [l.lat, l.lng]), { padding: [30, 30] });
    else map.setView([20, 0], 2);
    setTimeout(() => map.invalidateSize(), 100);
  }, [listings]);
  return <div className="mini-map" ref={ref} style={{ height }} />;
}

/* ----------------------------- Listing card ----------------------------- */
function Card({ l, onOpen, onLike }) {
  return (
    <div className="card" onClick={() => onOpen(l)}>
      <div className="photo" style={{ backgroundImage: `url(${l.image_url})` }}>
        <button className="fav" onClick={(e) => { e.stopPropagation(); onLike(l); }}>♥</button>
        {l.score > 0 && <span className="score">★ match {Math.round(l.score * 100)}%</span>}
      </div>
      <div className="body">
        <div className="row">
          <span className="title">{l.title}</span>
          <span className="star">★ {l.rating}</span>
        </div>
        <div className="loc">{l.city}, {l.country}</div>
        <div className="tags">{(l.tags || []).slice(0, 3).map((t) => <span key={t} className="tag">{t}</span>)}</div>
        <div className="row" style={{ marginTop: 8 }}>
          <span className="price">{l.price_is_estimate ? "≈ " : ""}{money(l.price_per_night)} <small>/ night</small></span>
        </div>
        {l.reason && <div className="reason">✦ {l.reason}</div>}
      </div>
    </div>
  );
}

/* ----------------------------- Listing modal ----------------------------- */
function ListingModal({ listing, user, onClose, toast }) {
  const today = new Date().toISOString().slice(0, 10);
  const [checkIn, setCheckIn] = useState(today);
  const [checkOut, setCheckOut] = useState(new Date(Date.now() + 3 * 864e5).toISOString().slice(0, 10));
  const [guests, setGuests] = useState(2);
  const [busy, setBusy] = useState(false);
  if (!listing) return null;
  const nights = Math.max(0, (new Date(checkOut) - new Date(checkIn)) / 864e5);
  const total = nights * listing.price_per_night;

  const book = async () => {
    if (!user) return toast("Please sign in to save this trip");
    setBusy(true);
    try {
      await api.call("/bookings", { method: "POST", body: {
        listing_id: listing.id, check_in: checkIn, check_out: checkOut, guests: Number(guests) } });
      toast(`Saved to your trips · ${money(total)}`);
      onClose();
    } catch (e) { toast(e.message); } finally { setBusy(false); }
  };

  const site = bookingSite(listing.booking_url);
  const bookExternal = () => {
    // Log the affiliate click as a strong signal, then open the partner site.
    if (user) api.call(`/listings/${listing.id}/interactions`, { method: "POST", body: { kind: "click" } }).catch(() => {});
    window.open(listing.booking_url, "_blank", "noopener");
  };

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="hd" style={{ backgroundImage: `url(${listing.image_url})` }}>
          <button className="close" onClick={onClose}>✕</button>
        </div>
        <div className="ct">
          <h2>{listing.title}</h2>
          <div className="muted">{listing.city}, {listing.country} · ★ {listing.rating} ({listing.review_count} reviews) · up to {listing.max_guests} guests</div>
          <p>{listing.description}</p>
          <div className="tags">{(listing.amenities || []).map((a) => <span key={a} className="tag">{a}</span>)}</div>
          <MiniMap listings={[listing]} />

          {listing.booking_url && (
            <div className="book-real">
              <div>
                <strong>Book this real stay</strong>
                <div className="muted" style={{ fontSize: 13 }}>
                  Live availability &amp; final price on {site}
                  {listing.source === "openstreetmap" && " · listing data from OpenStreetMap"}
                </div>
              </div>
              <button className="btn" onClick={bookExternal}>Check availability on {site} →</button>
            </div>
          )}

          <h3>Plan it on Wanderly</h3>
          <p className="muted" style={{ fontSize: 13, marginTop: -6 }}>
            Save these dates to your trips. {listing.price_is_estimate && "Price shown is an estimate — the live rate is on " + site + "."}
          </p>
          <div className="field-row">
            <label className="form">Check in<input type="date" value={checkIn} min={today} onChange={(e) => setCheckIn(e.target.value)} /></label>
            <label className="form">Check out<input type="date" value={checkOut} min={checkIn} onChange={(e) => setCheckOut(e.target.value)} /></label>
            <label className="form">Guests<input type="number" min="1" max={listing.max_guests} value={guests} onChange={(e) => setGuests(e.target.value)} /></label>
          </div>
          <div className="row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 14 }}>
            <strong>{listing.price_is_estimate ? "≈ " : ""}{money(listing.price_per_night)} × {nights} nights = {money(total)}</strong>
            <button className="btn ghost" onClick={book} disabled={busy || nights <= 0}>{busy ? "Saving…" : "Save to my trips"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ----------------------------- Explore view ----------------------------- */
function Explore({ user, openListing, toast }) {
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("relevance");
  const [tags, setTags] = useState([]);
  const [maxPrice, setMaxPrice] = useState("");
  const [results, setResults] = useState([]);
  const [recs, setRecs] = useState([]);
  const [suggestions, setSuggestions] = useState(null);
  const [loading, setLoading] = useState(true);
  const [showMap, setShowMap] = useState(false);

  const runSearch = useCallback(async () => {
    setLoading(true);
    try {
      const body = { q: q || null, sort, tags, personalize: true, limit: 24 };
      if (maxPrice) body.max_price = Number(maxPrice);
      const r = await api.call("/search", { method: "POST", body });
      setResults(r.results);
    } catch (e) { toast(e.message); } finally { setLoading(false); }
  }, [q, sort, tags, maxPrice, toast]);

  useEffect(() => { runSearch(); }, [sort, tags]);
  useEffect(() => {
    if (!user) { setRecs([]); setSuggestions(null); return; }
    api.call("/recommendations?limit=8").then(setRecs).catch(() => {});
    api.call("/recommendations/suggestions").then(setSuggestions).catch(() => {});
  }, [user]);

  const toggleTag = (t) => setTags((p) => p.includes(t) ? p.filter((x) => x !== t) : [...p, t]);
  const like = async (l) => {
    if (!user) return toast("Sign in to save favorites");
    try { await api.call(`/listings/${l.id}/interactions`, { method: "POST", body: { kind: "like" } });
      toast(`Saved ${l.title} ♥`); } catch (e) {}
  };

  return (
    <div className="container">
      <div className="hero">
        <h1>Find your next trip, personalized by AI</h1>
        <p>Search any destination in the world — real stays pulled live, ranked to your taste, with AI-built day-by-day itineraries.</p>
        <div className="searchbar">
          <input className="grow" placeholder="Search anywhere — e.g. Lisbon, Goa, Patagonia…" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runSearch()} />
          <input type="number" placeholder="Max $/night" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} style={{ width: 140 }} />
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="relevance">Best match</option>
            <option value="price_asc">Price: low to high</option>
            <option value="price_desc">Price: high to low</option>
            <option value="rating">Top rated</option>
          </select>
          <button className="btn" onClick={runSearch}>Search</button>
        </div>
      </div>

      <div className="filters">
        {ALL_TAGS.map((t) => (
          <button key={t} className={"chip" + (tags.includes(t) ? " on" : "")} onClick={() => toggleTag(t)}>{t}</button>
        ))}
        <span className="spacer" />
        <button className="chip" onClick={() => setShowMap((s) => !s)}>{showMap ? "Hide map" : "Show map"}</button>
      </div>

      {showMap && <div className="panel" style={{ padding: 0, overflow: "hidden" }}><MiniMap listings={results} height={320} /></div>}

      {user && suggestions && (
        <>
          <div className="section-title">AI suggestions for you <span className="badge">{suggestions.generated_by}</span></div>
          {suggestions.suggestions.map((s, i) => <div key={i} className="suggestion">💡 {s}</div>)}
        </>
      )}

      {user && recs.length > 0 && (
        <>
          <div className="section-title">Recommended for you</div>
          <div className="grid">{recs.map((l) => <Card key={"r" + l.id} l={l} onOpen={openListing} onLike={like} />)}</div>
        </>
      )}

      <div className="section-title">{q ? `Results for “${q}”` : "Explore stays"} <span className="muted" style={{ fontSize: 15 }}>({results.length})</span></div>
      {loading ? <div className="loading">Searching…</div> :
        results.length === 0 ? <div className="empty">No stays match those filters.</div> :
        <div className="grid">{results.map((l) => <Card key={l.id} l={l} onOpen={openListing} onLike={like} />)}</div>}
    </div>
  );
}

/* ----------------------------- Trips view ----------------------------- */
function Trips({ user, toast }) {
  const [destination, setDestination] = useState("Lisbon");
  const [days, setDays] = useState(3);
  const [trips, setTrips] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => { api.call("/trips").then(setTrips).catch(() => {}); }, []);
  useEffect(() => { if (user) load(); }, [user, load]);

  const plan = async () => {
    setBusy(true);
    try {
      await api.call("/trips", { method: "POST", body: { destination, days: Number(days) } });
      toast(`Itinerary for ${destination} created`);
      load();
    } catch (e) { toast(e.message); } finally { setBusy(false); }
  };
  const remove = async (id) => { await api.call(`/trips/${id}`, { method: "DELETE" }); load(); };

  if (!user) return <div className="container"><div className="empty">Sign in to plan AI itineraries.</div></div>;
  return (
    <div className="container">
      <div className="section-title">AI Trip Planner</div>
      <div className="searchbar" style={{ maxWidth: 620 }}>
        <input className="grow" placeholder="Destination" value={destination} onChange={(e) => setDestination(e.target.value)} />
        <input type="number" min="1" max="14" value={days} onChange={(e) => setDays(e.target.value)} style={{ width: 90 }} />
        <button className="btn" onClick={plan} disabled={busy}>{busy ? "Planning…" : "Generate itinerary"}</button>
      </div>

      {trips.length === 0 ? <div className="empty">No trips yet — generate your first itinerary above.</div> :
        trips.map((t) => (
          <div key={t.id} className="panel">
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <div>
                <h3 style={{ margin: "0 0 4px" }}>{t.title} <span className="badge">{t.generated_by}</span></h3>
                <div className="muted">{t.summary}</div>
              </div>
              <button className="btn ghost small" onClick={() => remove(t.id)}>Delete</button>
            </div>
            {t.days.map((d) => (
              <div key={d.day} className="day">
                <h4>{d.title}</h4>
                <ul>{(d.activities || []).map((a, i) => <li key={i}>{a}</li>)}</ul>
              </div>
            ))}
          </div>
        ))}
    </div>
  );
}

/* ----------------------------- Bookings view ----------------------------- */
function Bookings({ user, toast }) {
  const [items, setItems] = useState([]);
  const load = useCallback(() => { api.call("/bookings").then(setItems).catch(() => {}); }, []);
  useEffect(() => { if (user) load(); }, [user, load]);
  const cancel = async (id) => { await api.call(`/bookings/${id}/cancel`, { method: "POST" }); toast("Booking cancelled"); load(); };
  if (!user) return <div className="container"><div className="empty">Sign in to see your bookings.</div></div>;
  return (
    <div className="container">
      <div className="section-title">Your trips & bookings</div>
      {items.length === 0 ? <div className="empty">No bookings yet.</div> :
        <div className="grid">
          {items.map((b) => (
            <div key={b.id} className="card" style={{ cursor: "default" }}>
              <div className="photo" style={{ backgroundImage: `url(${b.listing && b.listing.image_url})` }} />
              <div className="body">
                <div className="title">{b.listing ? b.listing.title : "Listing #" + b.listing_id}</div>
                <div className="loc">{b.check_in} → {b.check_out} · {b.guests} guests</div>
                <div className="row" style={{ marginTop: 6 }}>
                  <span className="price">{money(b.total_price)}</span>
                  <span className={"tag"} style={{ background: b.status === "confirmed" ? "#e6f7ee" : "#fde8e8" }}>{b.status}</span>
                </div>
                {b.status === "confirmed" && <button className="btn ghost small" style={{ marginTop: 8 }} onClick={() => cancel(b.id)}>Cancel</button>}
              </div>
            </div>
          ))}
        </div>}
    </div>
  );
}

/* ----------------------------- Dashboard view ----------------------------- */
function Dashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.call("/analytics/dashboard").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="container"><div className="loading">Loading analytics…</div></div>;
  const maxEng = Math.max(1, ...d.engagement_by_day.map((e) => e.interactions));
  const maxTag = Math.max(1, ...d.popular_tags.map((t) => t.weight));
  const q = d.recommendation_quality;
  return (
    <div className="container">
      <div className="section-title">Platform Analytics</div>
      <div className="stats">
        <div className="stat"><div className="n">{d.totals.users}</div><div className="l">Users</div></div>
        <div className="stat"><div className="n">{d.totals.listings}</div><div className="l">Listings</div></div>
        <div className="stat"><div className="n">{d.totals.bookings}</div><div className="l">Bookings</div></div>
        <div className="stat"><div className="n">{d.totals.trips}</div><div className="l">AI Itineraries</div></div>
        <div className="stat"><div className="n">{money(d.totals.revenue)}</div><div className="l">Revenue</div></div>
        <div className="stat"><div className="n">{d.totals.interactions}</div><div className="l">Interactions</div></div>
      </div>

      <div className="two-col">
        <div className="panel">
          <h3>Recommendation quality</h3>
          <p className="muted">Served {q.served} · accepted {q.accepted}</p>
          <div className="bar-row"><span className="lbl">Acceptance rate</span>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${q.acceptance_rate * 100}%` }} /></div>
            <b>{Math.round(q.acceptance_rate * 100)}%</b></div>
          <div className="bar-row"><span className="lbl">Avg match score</span>
            <div className="bar-track"><div className="bar-fill" style={{ width: `${q.avg_score * 100}%`, background: "var(--accent)" }} /></div>
            <b>{Math.round(q.avg_score * 100)}%</b></div>
          <p className="muted" style={{ marginTop: 14 }}>Cache: <b>{d.cache_backend}</b> · LLM: <b>{d.llm_provider}</b></p>
        </div>
        <div className="panel">
          <h3>Popular tags</h3>
          {d.popular_tags.map((t) => (
            <div key={t.tag} className="bar-row"><span className="lbl">{t.tag}</span>
              <div className="bar-track"><div className="bar-fill" style={{ width: `${(t.weight / maxTag) * 100}%`, background: "var(--accent)" }} /></div></div>
          ))}
        </div>
      </div>

      <div className="panel">
        <h3>Engagement (interactions / day)</h3>
        {d.engagement_by_day.length === 0 ? <p className="muted">No activity yet.</p> :
          d.engagement_by_day.map((e) => (
            <div key={e.date} className="bar-row"><span className="lbl">{e.date}</span>
              <div className="bar-track"><div className="bar-fill" style={{ width: `${(e.interactions / maxEng) * 100}%` }} /></div>
              <b>{e.interactions}</b></div>
          ))}
      </div>

      <div className="panel">
        <h3>Top listings by popularity</h3>
        <div className="grid">
          {d.top_listings.map((l) => (
            <div key={l.id} className="stat"><div className="title">{l.title}</div>
              <div className="muted">{l.city} · ★ {l.rating}</div>
              <div className="n" style={{ fontSize: 20 }}>{l.popularity}</div><div className="l">popularity</div></div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ----------------------------- Auth view ----------------------------- */
function Auth({ onAuthed, toast }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "demo@traveler.io", password: "demo1234", name: "",
    budget: 200, climate: "warm", styles: "beach, city", interests: "food, art" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      let data;
      if (mode === "login") {
        data = await api.call("/auth/login", { method: "POST", body: { email: form.email, password: form.password } });
      } else {
        const preferences = {
          budget: Number(form.budget), climate: form.climate,
          trip_styles: form.styles.split(",").map((s) => s.trim()).filter(Boolean),
          interests: form.interests.split(",").map((s) => s.trim()).filter(Boolean),
        };
        data = await api.call("/auth/register", { method: "POST",
          body: { email: form.email, name: form.name || "Traveler", password: form.password, preferences } });
      }
      api.setToken(data.access_token);
      onAuthed(data.user);
      toast(`Welcome, ${data.user.name}!`);
    } catch (e) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="container">
      <div className="center-box">
        <h2>{mode === "login" ? "Sign in" : "Create account"}</h2>
        <p className="muted">Demo account is pre-filled — just click {mode === "login" ? "Sign in" : "below"}.</p>
        <div className="form">
          {mode === "register" && <label>Name<input value={form.name} onChange={set("name")} placeholder="Your name" /></label>}
          <label>Email<input value={form.email} onChange={set("email")} /></label>
          <label>Password<input type="password" value={form.password} onChange={set("password")} /></label>
          {mode === "register" && <>
            <div className="field-row">
              <label>Budget /night<input type="number" value={form.budget} onChange={set("budget")} /></label>
              <label>Climate
                <select value={form.climate} onChange={set("climate")}>
                  <option>warm</option><option>cold</option><option>temperate</option><option>any</option>
                </select></label>
            </div>
            <label>Trip styles<input value={form.styles} onChange={set("styles")} placeholder="beach, city" /></label>
            <label>Interests<input value={form.interests} onChange={set("interests")} placeholder="food, art" /></label>
          </>}
          {err && <div className="error">{err}</div>}
          <button className="btn" onClick={submit} disabled={busy}>{busy ? "…" : (mode === "login" ? "Sign in" : "Create account")}</button>
          <button className="btn ghost" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>
            {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ----------------------------- App shell ----------------------------- */
function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("explore");
  const [active, setActive] = useState(null);
  const [ready, setReady] = useState(false);
  const [toastNode, toast] = useToast();

  useEffect(() => {
    if (api.token()) api.call("/auth/me").then(setUser).catch(() => api.setToken(null)).finally(() => setReady(true));
    else setReady(true);
  }, []);

  const openListing = async (l) => {
    setActive(l);
    try { await api.call(`/listings/${l.id}/interactions`, { method: "POST", body: { kind: "click" } }); } catch (e) {}
  };
  const logout = () => { api.setToken(null); setUser(null); setView("explore"); toast("Signed out"); };
  const go = (v) => { if ((v === "trips" || v === "bookings") && !user) { setView("auth"); } else setView(v); };

  if (!ready) return <div className="loading">Loading…</div>;

  const nav = [["explore", "Explore"], ["trips", "AI Planner"], ["bookings", "Bookings"]];
  if (user && user.is_admin) nav.push(["dashboard", "Dashboard"]);
  return (
    <>
      <header className="header">
        <div className="logo" onClick={() => setView("explore")}>🧭 Wanderly</div>
        <nav className="nav">
          {nav.map(([k, label]) => (
            <button key={k} className={view === k ? "active" : ""} onClick={() => go(k)}>{label}</button>
          ))}
        </nav>
        <span className="spacer" />
        {user ? (
          <div className="user-chip">
            <div className="avatar">{user.name[0].toUpperCase()}</div>
            <span>{user.name}</span>
            <button className="btn ghost small" onClick={logout}>Sign out</button>
          </div>
        ) : (
          <button className="btn" onClick={() => setView("auth")}>Sign in</button>
        )}
      </header>

      {view === "explore" && <Explore user={user} openListing={openListing} toast={toast} />}
      {view === "trips" && <Trips user={user} toast={toast} />}
      {view === "bookings" && <Bookings user={user} toast={toast} />}
      {view === "dashboard" && <Dashboard />}
      {view === "auth" && <Auth onAuthed={(u) => { setUser(u); setView("explore"); }} toast={toast} />}

      {active && <ListingModal listing={active} user={user} onClose={() => setActive(null)} toast={toast} />}
      {toastNode}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
