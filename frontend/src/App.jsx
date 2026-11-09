import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";

const API = (
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"
).replace(/\/$/, "");

const CATEGORIES = [
  "Childhood",
  "Family",
  "Friends",
  "Travel",
  "Milestones",
  "Everyday Moments",
  "Other",
];

function App() {

  const [memories, setMemories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [language, setLanguage] = useState("hi-IN");

  const [selectedFile, setSelectedFile] = useState(null);
  const [recording, setRecording] = useState(false);
  const [recordedBlob, setRecordedBlob] = useState(null);
  const [recordingUrl, setRecordingUrl] = useState("");

  const [title, setTitle] = useState("");
  const [person, setPerson] = useState("");
  const [category, setCategory] = useState("Family");
  const [memoryDate, setMemoryDate] = useState(
    new Date().toISOString().slice(0, 10)
  );

  const [transcribing, setTranscribing] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [narratingId, setNarratingId] = useState(null);
  const [recap, setRecap] = useState(null);
  const [recapMonth, setRecapMonth] = useState(
    new Date().toISOString().slice(0, 7)
  );

  const fileInputRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    loadMemories();

    return () => {
      if (recordingUrl) URL.revokeObjectURL(recordingUrl);
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
    // Initial load only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredMemories = useMemo(() => {
    const term = search.trim().toLowerCase();

    return memories.filter((memory) => {
      const matchesSearch =
        !term ||
        [
          memory.title,
          memory.content,
          memory.original_transcript,
          memory.person,
        ]
          .filter(Boolean)
          .some((value) => value.toLowerCase().includes(term));

      const matchesCategory =
        !categoryFilter || memory.category === categoryFilter;

      return matchesSearch && matchesCategory;
    });
  }, [memories, search, categoryFilter]);

  async function loadMemories() {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API}/memories`);

      if (!response.ok) {
        throw new Error("Could not load memories.");
      }

      const data = await response.json();
      setMemories(data.memories || []);
    } catch (err) {
      setError(err.message || "Unable to connect to MaaMemo.");
    } finally {
      setLoading(false);
    }
  }

  function resetAudioSelection() {
    setSelectedFile(null);
    setRecordedBlob(null);

    if (recordingUrl) {
      URL.revokeObjectURL(recordingUrl);
      setRecordingUrl("");
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function handleFileChange(event) {
    const file = event.target.files?.[0];

    if (!file) return;

    const allowedExtensions = [
      ".wav", ".mp3", ".m4a", ".mp4", ".webm", ".ogg", ".mpeg",
    ];
    const extension = file.name
      .substring(file.name.lastIndexOf("."))
      .toLowerCase();

    if (!allowedExtensions.includes(extension)) {
      setError(
        "Unsupported file. Upload WAV, MP3, M4A, MP4, WebM, OGG or MPEG."
      );
      event.target.value = "";
      return;
    }

    if (file.size > 25 * 1024 * 1024) {
      setError("Please upload an audio file smaller than 25 MB.");
      event.target.value = "";
      return;
    }

    resetAudioSelection();
    setError("");
    setNotice(`Selected: ${file.name}`);
    setSelectedFile(file);
  }

  function getSupportedRecordingType() {
    if (!window.MediaRecorder) {
      throw new Error("Audio recording is not supported in this browser.");
    }

    const formats = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ];

    return formats.find((format) => MediaRecorder.isTypeSupported(format)) || "";
  }

  function getRecordingExtension(mimeType) {
    const mime = (mimeType || "").toLowerCase();

    if (mime.includes("mp4")) return "m4a";
    if (mime.includes("ogg")) return "ogg";
    if (mime.includes("webm")) return "webm";

    return "webm";
  }

  async function startRecording() {
    try {
      setError("");
      setNotice("");

      if (!window.isSecureContext) {
        throw new Error("Microphone access requires HTTPS or localhost.");
      }

      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error(
          "Microphone access is unavailable. Please use Chrome or Edge."
        );
      }

      if (!window.MediaRecorder) {
        throw new Error("Your browser does not support audio recording.");
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      streamRef.current = stream;
      chunksRef.current = [];

      const mimeType = getSupportedRecordingType();
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);

      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.onerror = (event) => {
        setError(
          event.error?.message || "An error occurred during recording."
        );
        setRecording(false);
      };

      recorder.onstop = () => {
        const actualType = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: actualType });

        if (blob.size === 0) {
          setError("No audio was recorded. Please try again.");
        } else {
          setRecordedBlob(blob);
          setRecordingUrl((previousUrl) => {
            if (previousUrl) URL.revokeObjectURL(previousUrl);
            return URL.createObjectURL(blob);
          });
          setNotice("Recording ready. You can now save your memory.");
        }

        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setRecording(false);
      };

      recorder.start(1000);
      setRecording(true);
      setNotice("Recording started. Speak naturally.");
    } catch (err) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setRecording(false);

      let message = err.message || "Could not start recording.";
      if (err.name === "NotAllowedError") {
        message =
          "Microphone permission denied. Allow microphone access in your browser settings.";
      } else if (err.name === "NotFoundError") {
        message = "No microphone was detected on this device.";
      } else if (err.name === "NotReadableError") {
        message = "Your microphone is being used by another application.";
      }

      setError(message);
    }
  }

  function stopRecording() {
    const recorder = mediaRecorderRef.current;

    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  async function saveVoiceMemory(event) {
    event.preventDefault();

    const audioFile =
      selectedFile ||
      (recordedBlob
        ? new File(
            [recordedBlob],
            `maamemo-recording.${getRecordingExtension(recordedBlob.type)}`,
            { type: recordedBlob.type || "audio/webm" }
          )
        : null);

    if (!audioFile) {
      setError("Please upload an audio file or record a memory first.");
      return;
    }

    setTranscribing(true);
    setError("");
    setNotice("");

    const formData = new FormData();
    formData.append("audio", audioFile);
    formData.append("language_code", language);

    if (title.trim()) formData.append("title", title.trim());
    if (category) formData.append("category", category);
    if (person.trim()) formData.append("person", person.trim());
    if (memoryDate) formData.append("memory_date", memoryDate);

    try {
      const response = await fetch(`${API}/memories/from-audio`, {
        method: "POST",
        body: formData,
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not save this voice memory.");
      }

      setNotice("Your memory has been saved successfully.");
      setTitle("");
      setPerson("");
      setCategory("Family");
      setMemoryDate(new Date().toISOString().slice(0, 10));
      resetAudioSelection();

      await loadMemories();
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setTranscribing(false);
    }
  }

  async function narrateMemory(memoryId) {
    setNarratingId(memoryId);
    setError("");
    setNotice("");

    try {
      const response = await fetch(
        `${API}/memories/${memoryId}/narrate`,
        { method: "POST" }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Narration could not be generated.");
      }

      setNotice("AI narration generated successfully.");
      await loadMemories();
    } catch (err) {
      setError(err.message || "Narration failed.");
    } finally {
      setNarratingId(null);
    }
  }

  function startEditing(memory) {
    setEditingId(memory.id);
    setEditForm({
      title: memory.title || "",
      content: memory.content || "",
      person: memory.person || "",
      category: memory.category || "",
      language: memory.language || "hi-IN",
      memory_date: memory.memory_date || "",
    });
  }

  async function saveEdit(memoryId) {
    setError("");

    try {
      const response = await fetch(`${API}/memories/${memoryId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(editForm),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not update memory.");
      }

      setEditingId(null);
      setNotice("Memory updated successfully.");
      await loadMemories();
    } catch (err) {
      setError(err.message || "Update failed.");
    }
  }

  async function deleteMemory(memoryId) {
    const confirmed = window.confirm(
      "Are you sure you want to permanently delete this memory and its saved audio?"
    );

    if (!confirmed) return;

    setError("");

    try {
      const response = await fetch(`${API}/memories/${memoryId}`, {
        method: "DELETE",
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not delete memory.");
      }

      setNotice("Memory deleted.");
      await loadMemories();
    } catch (err) {
      setError(err.message || "Delete failed.");
    }
  }

  async function loadMonthlyRecap(event) {
    event.preventDefault();

    if (!recapMonth) return;

    const [year, month] = recapMonth.split("-");

    try {
      const response = await fetch(
        `${API}/recap/${year}/${Number(month)}`
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not load monthly recap.");
      }

      setRecap(data);
      setError("");
    } catch (err) {
      setError(err.message || "Could not load recap.");
    }
  }

  function audioUrl(path) {
    if (!path) return "";
    return path.startsWith("http") ? path : `${API}${path}`;
  }

  function formatDate(value) {
    if (!value) return "Date not specified";

    return new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#home">
          <span className="brand-mark">M</span>
          <span>
            <strong>MaaMemo</strong>
            <small>Every memory deserves a home.</small>
          </span>
        </a>

        <nav className="top-nav">
          <a href="#home">Home</a>
          <a href="#create">Create memory</a>
          <a href="#library">My memories</a>
        </nav>

        <span className="top-pill">Your personal memory book</span>
      </header>

      <main id="home">
        <section className="hero-section">
          <div className="hero-copy">
            <span className="eyebrow">A LITTLE PLACE FOR YOUR FOREVER</span>
            <h1>
              Keep the moments.
              <br />
              <span>Keep them close.</span>
            </h1>
            <p>
              Save the stories, voices and little moments that make life yours.
              MaaMemo turns your spoken memories into a personal digital
              keepsake.
            </p>

            <a className="primary-button hero-button" href="#create">
              <span>＋</span> Save a memory
            </a>

            <div className="hero-note">
              <span>✦</span> Powered by Gnani AI voice technology
            </div>
          </div>

          <div className="hero-art" aria-label="Memory book illustration">
            <div className="art-sun" />
            <div className="art-card art-card-back">
              <span>little moments</span>
              <div className="art-lines" />
            </div>
            <div className="art-card art-card-front">
              <span className="art-heart">♡</span>
              <p>Some moments<br />stay forever.</p>
              <small>MAAMEMO · MEMORY NO. 001</small>
            </div>
            <span className="floating-star star-one">✳</span>
            <span className="floating-star star-two">✦</span>
            <span className="floating-text">made of memories</span>
          </div>
        </section>

        <section className="stats-row">
          <div className="stat-card">
            <span className="stat-icon">▤</span>
            <div>
              <strong>{memories.length}</strong>
              <small>Memories saved</small>
            </div>
          </div>
          <div className="stat-card">
            <span className="stat-icon">♡</span>
            <div>
              <strong>{new Set(memories.map((m) => m.person).filter(Boolean)).size}</strong>
              <small>People remembered</small>
            </div>
          </div>
          <div className="stat-card">
            <span className="stat-icon">♫</span>
            <div>
              <strong>{memories.filter((m) => m.audio_path).length}</strong>
              <small>Voice recordings</small>
            </div>
          </div>
        </section>

        {error && (
          <div className="alert alert-error" role="alert">
            {error}
            <button onClick={() => setError("")}>×</button>
          </div>
        )}

        {notice && (
          <div className="alert alert-success" role="status">
            {notice}
            <button onClick={() => setNotice("")}>×</button>
          </div>
        )}

        <section className="create-section" id="create">
          <div className="section-heading">
            <div>
              <span className="eyebrow">CAPTURE A MOMENT</span>
              <h2>Save a new memory</h2>
              <p>Tell your story. We'll help you preserve it.</p>
            </div>
            <span className="section-decoration">✿</span>
          </div>

          <form className="memory-form" onSubmit={saveVoiceMemory}>
            <div className="form-main">
              <div className="form-label-row">
                <label className="field-label">Your recording</label>
                <span className="field-hint">MP3 and WAV recommended</span>
              </div>

              <div className="audio-actions">
                <button
                  type="button"
                  className={`record-button ${recording ? "is-recording" : ""}`}
                  onClick={recording ? stopRecording : startRecording}
                >
                  <span className="record-dot" />
                  {recording ? "Stop recording" : "Start recording"}
                </button>

                <span className="or-divider">or</span>

                <button
                  type="button"
                  className="upload-button"
                  onClick={() => fileInputRef.current?.click()}
                >
                  ↑ Upload audio
                </button>

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".wav,.mp3,.m4a,.mp4,.webm,.ogg,.mpeg,audio/*"
                  hidden
                  onChange={handleFileChange}
                />
              </div>

              {selectedFile && (
                <div className="file-preview">
                  <span>♫</span>
                  <span>{selectedFile.name}</span>
                  <button type="button" onClick={resetAudioSelection}>Remove</button>
                </div>
              )}

              {recordedBlob && recordingUrl && (
                <div className="recorded-preview">
                  <span>Recording ready</span>
                  <audio controls src={recordingUrl} />
                  <button type="button" onClick={resetAudioSelection}>Discard</button>
                </div>
              )}

              {recording && (
                <p className="recording-hint">
                  ● Recording in progress — speak naturally, then press Stop.
                </p>
              )}

              <div className="field-group">
                <label className="field-label" htmlFor="memory-title">
                  Memory title <span className="optional">(optional)</span>
                </label>
                <input
                  id="memory-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. A summer at Nani's house"
                />
              </div>

              <div className="form-grid">
                <div className="field-group">
                  <label className="field-label" htmlFor="memory-person">
                    Who is in this memory?
                  </label>
                  <input
                    id="memory-person"
                    value={person}
                    onChange={(e) => setPerson(e.target.value)}
                    placeholder="e.g. Grandmother"
                  />
                </div>

                <div className="field-group">
                  <label className="field-label" htmlFor="memory-category">
                    Category
                  </label>
                  <select
                    id="memory-category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                  >
                    {CATEGORIES.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </select>
                </div>

                <div className="field-group">
                  <label className="field-label" htmlFor="memory-date">
                    When did it happen?
                  </label>
                  <input
                    id="memory-date"
                    type="date"
                    value={memoryDate}
                    onChange={(e) => setMemoryDate(e.target.value)}
                  />
                </div>

                <div className="field-group">
                  <label className="field-label" htmlFor="memory-language">
                    Recording language
                  </label>
                  <select
                    id="memory-language"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    <option value="hi-IN">Hindi</option>
                    <option value="en-IN">English (India)</option>
                  </select>
                </div>
              </div>

              <button
                className="primary-button save-button"
                type="submit"
                disabled={transcribing || recording || (!selectedFile && !recordedBlob)}
              >
                {transcribing ? "Transcribing and saving..." : "✦  Preserve this memory"}
              </button>
              <p className="privacy-note">
                Your recording is saved in your MaaMemo application.
              </p>
            </div>

            <aside className="form-aside">
              <div className="aside-icon">♫</div>
              <h3>Your voice, your story.</h3>
              <p>
                MaaMemo uses Gnani Prisma to turn spoken memories into text.
                You can revisit the original recording whenever you like.
              </p>
              <div className="aside-divider" />
              <div className="aside-feature">
                <span>01</span>
                <p><strong>Speak freely</strong><br />Hindi or English memories.</p>
              </div>
              <div className="aside-feature">
                <span>02</span>
                <p><strong>Save the details</strong><br />Add a title, person and date.</p>
              </div>
              <div className="aside-feature">
                <span>03</span>
                <p><strong>Listen again</strong><br />Keep the voice that tells the story.</p>
              </div>
            </aside>
          </form>
        </section>

        <section className="library-section" id="library">
          <div className="section-heading library-heading">
            <div>
              <span className="eyebrow">YOUR PERSONAL COLLECTION</span>
              <h2>Memory library</h2>
              <p>All the moments you've chosen to keep.</p>
            </div>
            <button className="text-button" onClick={loadMemories}>
              ↻ Refresh memories
            </button>
          </div>

          <div className="library-tools">
            <div className="search-box">
              <span>⌕</span>
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search memories, people or stories..."
              />
            </div>

            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              aria-label="Filter by category"
            >
              <option value="">All categories</option>
              {CATEGORIES.map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </div>

          {loading ? (
            <div className="empty-state">Loading your memories...</div>
          ) : filteredMemories.length === 0 ? (
            <div className="empty-state">
              <span className="empty-icon">♡</span>
              <h3>No memories here yet</h3>
              <p>
                {memories.length
                  ? "Try another search or category."
                  : "Your first memory is waiting to be saved."}
              </p>
              {!memories.length && (
                <a className="primary-button" href="#create">Create your first memory</a>
              )}
            </div>
          ) : (
            <div className="memory-grid">
              {filteredMemories.map((memory) => (
                <article className="memory-card" key={memory.id}>
                  <div className="memory-card-top">
                    <span className="memory-category">
                      {memory.category || "Personal"}
                    </span>
                    <span className="memory-number">
                      #{String(memory.id).padStart(3, "0")}
                    </span>
                  </div>

                  {editingId === memory.id ? (
                    <div className="edit-form">
                      <input
                        value={editForm.title}
                        onChange={(e) =>
                          setEditForm({ ...editForm, title: e.target.value })
                        }
                        placeholder="Memory title"
                      />
                      <textarea
                        value={editForm.content}
                        onChange={(e) =>
                          setEditForm({ ...editForm, content: e.target.value })
                        }
                        rows={4}
                      />
                      <input
                        value={editForm.person}
                        onChange={(e) =>
                          setEditForm({ ...editForm, person: e.target.value })
                        }
                        placeholder="Person"
                      />
                      <select
                        value={editForm.category}
                        onChange={(e) =>
                          setEditForm({ ...editForm, category: e.target.value })
                        }
                      >
                        <option value="">No category</option>
                        {CATEGORIES.map((item) => (
                          <option key={item} value={item}>{item}</option>
                        ))}
                      </select>
                      <input
                        type="date"
                        value={editForm.memory_date || ""}
                        onChange={(e) =>
                          setEditForm({ ...editForm, memory_date: e.target.value })
                        }
                      />
                      <div className="card-actions">
                        <button onClick={() => saveEdit(memory.id)}>Save changes</button>
                        <button className="secondary-action" onClick={() => setEditingId(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <h3>{memory.title || "Untitled memory"}</h3>
                      <p className="memory-content">{memory.content}</p>

                      <div className="memory-meta">
                        {memory.person && <span>♡ {memory.person}</span>}
                        <span>◷ {formatDate(memory.memory_date)}</span>
                        <span>{memory.language || "Language not specified"}</span>
                      </div>

                      {memory.audio_path && (
                        <div className="audio-player">
                          <small>Original recording</small>
                          <audio controls preload="none" src={audioUrl(memory.audio_path)} />
                        </div>
                      )}

                      {memory.narration_path && (
                        <div className="audio-player narration-player">
                          <small>AI narration · Gnani Timbre</small>
                          <audio controls preload="none" src={audioUrl(memory.narration_path)} />
                        </div>
                      )}

                      <div className="card-actions">
                        <button
                          onClick={() => narrateMemory(memory.id)}
                          disabled={narratingId === memory.id}
                        >
                          {narratingId === memory.id
                            ? "Generating..."
                            : "♫ Generate narration"}
                        </button>
                        <button
                          className="secondary-action"
                          onClick={() => startEditing(memory)}
                        >
                          Edit
                        </button>
                        <button
                          className="delete-action"
                          onClick={() => deleteMemory(memory.id)}
                        >
                          Delete
                        </button>
                      </div>
                    </>
                  )}
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="recap-section" id="recap">
          <div>
            <span className="eyebrow">LOOKING BACK</span>
            <h2>A month of memories</h2>
            <p>Revisit the moments you saved in a particular month.</p>
          </div>

          <form className="recap-form" onSubmit={loadMonthlyRecap}>
            <input
              type="month"
              value={recapMonth}
              onChange={(e) => setRecapMonth(e.target.value)}
              required
            />
            <button className="primary-button" type="submit">View recap</button>
          </form>

          {recap && (
            <div className="recap-result">
              <h3>
                {new Date(recap.year, recap.month - 1).toLocaleDateString(
                  "en-IN",
                  { month: "long", year: "numeric" }
                )}
              </h3>
              <p>{recap.total_memories} memories saved that month.</p>
              {recap.memories.map((item) => (
                <div className="recap-item" key={item.id}>
                  <strong>{item.title}</strong>
                  <span>{formatDate(item.memory_date)}</span>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      <footer className="footer">
        <a className="brand footer-brand" href="#home">
          <span className="brand-mark">M</span>
          <strong>MaaMemo</strong>
        </a>
        <p>Made to keep the moments that matter. ♡</p>
        <span>Powered by Gnani AI</span>
      </footer>
    </div>
  );
}

export default App;