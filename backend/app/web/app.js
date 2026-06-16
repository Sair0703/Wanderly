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
const dealClass = (deal) =>
  deal === "Great deal" || deal === "Good value" ? "good" : deal === "Premium" ? "premium" : "neutral";

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
function Card({ l, onOpen, onToggleFav, saved }) {
  const isSaved = saved && saved.has(l.id);
  return (
    <div className="card" onClick={() => onOpen(l)}>
      <div className="photo" style={{ backgroundImage: `url(${l.image_url})` }}>
        <button className={"fav" + (isSaved ? " on" : "")} onClick={(e) => { e.stopPropagation(); onToggleFav(l); }}>♥</button>
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
          {l.deal && <span className={"deal " + dealClass(l.deal)}>{l.deal}</span>}
        </div>
        {l.reason && <div className="reason">✦ {l.reason}</div>}
      </div>
    </div>
  );
}

/* ----------------------------- Listing modal ----------------------------- */
function Reviews({ listing, user, toast }) {
  const [data, setData] = useState(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.call(`/listings/${listing.id}/reviews`).then(setData).catch(() => {});
  }, [listing.id]);
  useEffect(() => { load(); }, [load]);

  const submit = async () => {
    if (!user) return toast("Sign in to leave a review");
    setBusy(true);
    try {
      await api.call(`/listings/${listing.id}/reviews`, { method: "POST", body: { rating: Number(rating), comment } });
      setComment(""); toast("Review posted"); load();
    } catch (e) { toast(e.message); } finally { setBusy(false); }
  };

  return (
    <div>
      <h3>Guest reviews {data && data.count > 0 && <span className="muted">· ★ {data.average} ({data.count})</span>}</h3>
      {data && data.summary && (
        <div className="ai-summary">🤖 <b>AI summary:</b> {data.summary}</div>
      )}
      {data && data.reviews.length === 0 && <p className="muted">No reviews yet — be the first.</p>}
      {data && data.reviews.map((r) => (
        <div key={r.id} className="review">
          <div><b>{r.user_name}</b> <span className="star">{"★".repeat(r.rating)}</span></div>
          {r.comment && <div className="muted">{r.comment}</div>}
        </div>
      ))}
      <div className="review-form">
        <select value={rating} onChange={(e) => setRating(e.target.value)}>
          {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{"★".repeat(n)}</option>)}
        </select>
        <input placeholder="Share your experience…" value={comment} onChange={(e) => setComment(e.target.value)} />
        <button className="btn small" onClick={submit} disabled={busy}>Post</button>
      </div>
    </div>
  );
}

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

          <hr style={{ border: "none", borderTop: "1px solid var(--line)", margin: "20px 0" }} />
          <Reviews listing={listing} user={user} toast={toast} />
        </div>
      </div>
    </div>
  );
}

/* ----------------------------- Explore view ----------------------------- */
function Explore({ user, openListing, toast, saved, onToggleFav }) {
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
          <div className="grid">{recs.map((l) => <Card key={"r" + l.id} l={l} onOpen={openListing} onToggleFav={onToggleFav} saved={saved} />)}</div>
        </>
      )}

      <div className="section-title">{q ? `Results for “${q}”` : "Explore stays"} <span className="muted" style={{ fontSize: 15 }}>({results.length})</span></div>
      {loading ? <div className="loading">Searching…</div> :
        results.length === 0 ? <div className="empty">No stays match those filters.</div> :
        <div className="grid">{results.map((l) => <Card key={l.id} l={l} onOpen={openListing} onToggleFav={onToggleFav} saved={saved} />)}</div>}
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
  const share = async (t) => {
    const url = `${location.origin}/?trip=${t.share_id}`;
    try { await navigator.clipboard.writeText(url); toast("Share link copied to clipboard"); }
    catch (e) { window.prompt("Copy this share link:", url); }
  };

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
              <div style={{ display: "flex", gap: 8 }}>
                {t.share_id && <button className="btn ghost small" onClick={() => share(t)}>🔗 Share</button>}
                <button className="btn ghost small" onClick={() => remove(t.id)}>Delete</button>
              </div>
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

/* ----------------------------- AI Concierge ----------------------------- */
const CONCIERGE_EXAMPLES = [
  "A beachfront place in Barcelona under $170 for 4",
  "Romantic stay in Kyoto with a garden",
  "Cheap hostel in Lisbon for solo travel",
  "Ski chalet in the mountains for 6 people",
];

function Concierge({ user, openListing, toast, saved, onToggleFav }) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([
    { from: "bot", text: "Hi! Tell me about your trip in plain English and I'll find stays — e.g. “a beachfront place in Bali under $120 for 2”." },
  ]);
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);

  const send = async (text) => {
    const msg = (text || input).trim();
    if (!msg) return;
    setMessages((m) => [...m, { from: "user", text: msg }]);
    setInput(""); setBusy(true);
    try {
      const r = await api.call("/concierge", { method: "POST", body: { message: msg } });
      const u = r.understood;
      const chips = [u.destination && `📍 ${u.destination}`, u.max_price && `💰 ≤ $${Math.round(u.max_price)}`,
        u.guests && `👥 ${u.guests}`, ...(u.tags || []).map((t) => `#${t}`)].filter(Boolean);
      setMessages((m) => [...m, { from: "bot", text: r.reply, chips }]);
      setResults(r.results);
    } catch (e) { toast(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="container">
      <div className="concierge-wrap">
        <div className="section-title">AI Concierge <span className="badge">beta</span></div>
        <div className="chat">
          {messages.map((m, i) => (
            <div key={i}>
              <div className={"bubble " + m.from}>{m.text}</div>
              {m.chips && m.chips.length > 0 && <div className="chips-row">{m.chips.map((c, j) => <span key={j} className="chip on">{c}</span>)}</div>}
            </div>
          ))}
          {busy && <div className="bubble bot">Searching…</div>}
        </div>
        <div className="searchbar" style={{ marginTop: 12 }}>
          <input className="grow" placeholder="Describe your ideal trip…" value={input}
            onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} />
          <button className="btn" onClick={() => send()} disabled={busy}>Ask</button>
        </div>
        <div className="examples">
          {CONCIERGE_EXAMPLES.map((ex) => <button key={ex} onClick={() => send(ex)}>{ex}</button>)}
        </div>
      </div>
      {results.length > 0 && (
        <>
          <div className="section-title">Matches</div>
          <div className="grid">{results.map((l) => <Card key={l.id} l={l} onOpen={openListing} onToggleFav={onToggleFav} saved={saved} />)}</div>
        </>
      )}
    </div>
  );
}

/* ----------------------------- Saved view ----------------------------- */
function Saved({ user, openListing, toast, saved, onToggleFav }) {
  const [items, setItems] = useState([]);
  const load = useCallback(() => { api.call("/auth/me/favorites").then((d) => setItems(d.listings)).catch(() => {}); }, []);
  useEffect(() => { if (user) load(); }, [user, load, saved]);
  if (!user) return <div className="container"><div className="empty">Sign in to see your saved stays.</div></div>;
  return (
    <div className="container">
      <div className="section-title">Saved stays</div>
      {items.length === 0 ? <div className="empty">No saved stays yet — tap the ♥ on any listing.</div> :
        <div className="grid">{items.map((l) => <Card key={l.id} l={l} onOpen={openListing} onToggleFav={onToggleFav} saved={saved} />)}</div>}
    </div>
  );
}

/* ----------------------------- Shared trip (public) ----------------------------- */
function SharedTrip({ shareId }) {
  const [trip, setTrip] = useState(undefined);
  useEffect(() => {
    api.call(`/trips/shared/${shareId}`).then(setTrip).catch(() => setTrip(null));
  }, [shareId]);

  const goHome = () => { window.history.replaceState({}, "", "/"); location.reload(); };

  if (trip === undefined) return <div className="loading">Loading shared trip…</div>;
  if (trip === null) return (
    <div className="container"><div className="empty">This shared trip wasn't found.
      <div style={{ marginTop: 16 }}><button className="btn" onClick={goHome}>Explore Wanderly</button></div></div></div>
  );
  return (
    <>
      <header className="header">
        <div className="logo" onClick={goHome}>🧭 Wanderly</div>
        <span className="spacer" />
        <button className="btn" onClick={goHome}>Plan your own trip →</button>
      </header>
      <div className="container">
        <div className="hero">
          <h1>{trip.title}</h1>
          <p>{trip.summary}</p>
          <div className="muted" style={{ color: "rgba(255,255,255,.85)" }}>Shared by {trip.author} · made with AI</div>
        </div>
        {trip.days.map((d) => (
          <div key={d.day} className="panel">
            <h3 style={{ margin: "0 0 8px" }}>{d.title}</h3>
            <ul>{(d.activities || []).map((a, i) => <li key={i}>{a}</li>)}</ul>
          </div>
        ))}
        {trip.listings && trip.listings.length > 0 && (
          <>
            <div className="section-title">Where to stay</div>
            <div className="grid">{trip.listings.map((l) =>
              <Card key={l.id} l={l} onOpen={() => {}} onToggleFav={() => {}} saved={new Set()} />)}</div>
          </>
        )}
      </div>
    </>
  );
}

/* ----------------------------- App shell ----------------------------- */
function App() {
  const sharedTripId = new URLSearchParams(location.search).get("trip");
  if (sharedTripId) return <SharedTrip shareId={sharedTripId} />;
  const [user, setUser] = useState(null);
  const [view, setView] = useState("explore");
  const [active, setActive] = useState(null);
  const [ready, setReady] = useState(false);
  const [saved, setSaved] = useState(new Set());
  const [toastNode, toast] = useToast();

  const loadFavorites = useCallback(() => {
    api.call("/auth/me/favorites").then((d) => setSaved(new Set(d.ids))).catch(() => {});
  }, []);

  useEffect(() => {
    if (api.token()) api.call("/auth/me").then((u) => { setUser(u); loadFavorites(); })
      .catch(() => api.setToken(null)).finally(() => setReady(true));
    else setReady(true);
  }, [loadFavorites]);

  const openListing = async (l) => {
    setActive(l);
    try { await api.call(`/listings/${l.id}/interactions`, { method: "POST", body: { kind: "click" } }); } catch (e) {}
  };
  const toggleFav = async (l) => {
    if (!user) { toast("Sign in to save favorites"); setView("auth"); return; }
    try {
      const r = await api.call(`/listings/${l.id}/favorite`, { method: "POST" });
      setSaved((prev) => { const n = new Set(prev); r.saved ? n.add(l.id) : n.delete(l.id); return n; });
      toast(r.saved ? `Saved ${l.title} ♥` : `Removed ${l.title}`);
    } catch (e) { toast(e.message); }
  };
  const logout = () => { api.setToken(null); setUser(null); setSaved(new Set()); setView("explore"); toast("Signed out"); };
  const go = (v) => { if (["trips", "bookings", "saved"].includes(v) && !user) { setView("auth"); } else setView(v); };

  if (!ready) return <div className="loading">Loading…</div>;

  const nav = [["explore", "Explore"], ["concierge", "AI Concierge"], ["trips", "AI Planner"],
    ["saved", "Saved"], ["bookings", "Bookings"]];
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

      {view === "explore" && <Explore user={user} openListing={openListing} toast={toast} saved={saved} onToggleFav={toggleFav} />}
      {view === "concierge" && <Concierge user={user} openListing={openListing} toast={toast} saved={saved} onToggleFav={toggleFav} />}
      {view === "trips" && <Trips user={user} toast={toast} />}
      {view === "saved" && <Saved user={user} openListing={openListing} toast={toast} saved={saved} onToggleFav={toggleFav} />}
      {view === "bookings" && <Bookings user={user} toast={toast} />}
      {view === "dashboard" && <Dashboard />}
      {view === "auth" && <Auth onAuthed={(u) => { setUser(u); setView("explore"); loadFavorites(); }} toast={toast} />}

      {active && <ListingModal listing={active} user={user} onClose={() => setActive(null)} toast={toast} />}
      {toastNode}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
