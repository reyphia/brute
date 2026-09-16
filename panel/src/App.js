import React, { useState, useEffect, useRef } from 'react';
import { auth, db, firebaseConfigured } from './firebase';
import { signInWithEmailAndPassword, signOut } from 'firebase/auth';
import { collection, addDoc, query, orderBy, onSnapshot, doc, updateDoc, deleteDoc, getDoc } from 'firebase/firestore';

function FirebaseNotConfigured() {
  return (
    <div style={{ maxWidth: 520, margin: '100px auto', padding: 20, border: '1px solid #f0b429', borderRadius: 8, background: '#fffbea' }}>
      <h2>Firebase is not configured</h2>
      <p>
        Copy <code>panel/.env.example</code> to <code>panel/.env</code> and fill it in with
        your Firebase project's details (Project settings → General → Your apps),
        then restart the app.
      </p>
    </div>
  );
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await signInWithEmailAndPassword(auth, email, password);
      onLogin();
    } catch (err) {
      setError('Invalid login or password');
    }
  };
  return (
    <div style={{ maxWidth: 400, margin: '100px auto', padding: 20, border: '1px solid #ccc', borderRadius: 8 }}>
      <h2>Login</h2>
      <form onSubmit={handleSubmit}>
        <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required style={{ width: '100%', marginBottom: 10, padding: 8 }} />
        <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required style={{ width: '100%', marginBottom: 10, padding: 8 }} />
        <button type="submit" style={{ width: '100%', padding: 8 }}>Login</button>
        {error && <p style={{ color: 'red' }}>{error}</p>}
      </form>
    </div>
  );
}

function App() {
  const [user, setUser] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [hashFile, setHashFile] = useState(null);
  const [dicts, setDicts] = useState([]);
  const [rules, setRules] = useState([]);
  const [selectedDict, setSelectedDict] = useState('');
  const [selectedRule, setSelectedRule] = useState('');
  
  // Mask attack state
  const [useMask, setUseMask] = useState(false);
  const [maskLength, setMaskLength] = useState(8);
  const [maskLower, setMaskLower] = useState(true);
  const [maskUpper, setMaskUpper] = useState(true);
  const [maskDigits, setMaskDigits] = useState(true);
  const [maskSpecial, setMaskSpecial] = useState(false);
  const [customMask, setCustomMask] = useState('');

  const fileInputRef = useRef(null);

  useEffect(() => {
    if (!firebaseConfigured) return undefined;
    const unsubscribeAuth = auth.onAuthStateChanged(setUser);
    return () => unsubscribeAuth();
  }, []);

  // Load dicts/rules from Firestore
  useEffect(() => {
    if (!user) return;
    const configRef = doc(db, 'metadata', 'dictionary_rules');
    const fetchConfig = async () => {
      const snap = await getDoc(configRef);
      if (snap.exists()) {
        const data = snap.data();
        setDicts(data.dicts || []);
        setRules(data.rules || []);
        if (data.dicts.length) setSelectedDict(data.dicts[0].name);
        if (data.rules.length) setSelectedRule(data.rules[0].name);
      }
    };
    fetchConfig();
  }, [user]);

  // Listen tasks
  useEffect(() => {
    if (!user) return;
    const q = query(collection(db, 'tasks'), orderBy('createdAt', 'desc'));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const updated = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setTasks(updated);
    });
    return unsubscribe;
  }, [user]);

  // Generate mask pattern based on user choices
  const generateMask = () => {
    if (customMask.trim() !== '') return customMask.trim();
    let chars = '';
    if (maskLower) chars += '?l';
    if (maskUpper) chars += '?u';
    if (maskDigits) chars += '?d';
    if (maskSpecial) chars += '?s';
    if (chars === '') chars = '?l'; // fallback
    // Repeat the pattern for the given length
    let pattern = '';
    for (let i = 0; i < maskLength; i++) {
      pattern += chars;
    }
    return pattern;
  };

  const createTask = async () => {
    if (!hashFile) return;
    const content = await hashFile.text();
    const taskData = {
      hash: content,
      status: 'pending',
      progress: 0,
      result: null,
      createdAt: Date.now(),
      userId: user.uid
    };
    if (useMask) {
      // Attack mode: mask (-a 3)
      taskData.attack_mode = 'mask';
      taskData.mask = generateMask();
    } else {
      // Dictionary attack
      taskData.attack_mode = 'dict';
      taskData.dict = selectedDict;
      taskData.rule = selectedRule;
    }
    await addDoc(collection(db, 'tasks'), taskData);
    setHashFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    alert('Task sent to agent');
  };

  const cancelTask = async (taskId) => {
    if (!window.confirm('Cancel this task?')) return;
    await updateDoc(doc(db, 'tasks', taskId), { status: 'cancelling' });
  };

  const deleteTask = async (taskId) => {
    if (!window.confirm('Delete task from history?')) return;
    await deleteDoc(doc(db, 'tasks', taskId));
  };

  const handleLogout = async () => {
    await signOut(auth);
  };

  if (!firebaseConfigured) {
    return <FirebaseNotConfigured />;
  }

  if (!user) {
    return <Login onLogin={() => {}} />;
  }

  return (
    <div style={{ padding: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1>WPA2 Hash Cracker</h1>
        <button onClick={handleLogout}>Logout</button>
      </div>

      <div>
        <input type="file" accept=".hc22000,.txt" onChange={e => setHashFile(e.target.files[0])} ref={fileInputRef} />
      </div>

      {/* Attack mode selector */}
      <div style={{ margin: '20px 0', padding: '10px', border: '1px solid #ddd', borderRadius: 8 }}>
        <label style={{ marginRight: 20 }}>
          <input type="radio" checked={!useMask} onChange={() => setUseMask(false)} /> Dictionary attack
        </label>
        <label>
          <input type="radio" checked={useMask} onChange={() => setUseMask(true)} /> Mask attack
        </label>
      </div>

      {!useMask ? (
        <>
          <div style={{ margin: '10px 0' }}>
            <label>Dictionary: </label>
            <select value={selectedDict} onChange={e => setSelectedDict(e.target.value)}>
              {dicts.map(d => <option key={d.name} value={d.name}>{d.name} {d.type === 'folder' ? '📁' : '📄'}</option>)}
            </select>
          </div>
          <div style={{ margin: '10px 0' }}>
            <label>Rule: </label>
            <select value={selectedRule} onChange={e => setSelectedRule(e.target.value)}>
              {rules.map(r => <option key={r.name} value={r.name}>{r.name}</option>)}
            </select>
          </div>
        </>
      ) : (
        <div style={{ margin: '10px 0', padding: '10px', border: '1px solid #ddd', borderRadius: 8 }}>
          <h4>Mask settings</h4>
          <div>
            <label>Password length: </label>
            <input type="number" min="1" max="32" value={maskLength} onChange={e => setMaskLength(parseInt(e.target.value) || 8)} style={{ width: 60 }} />
            <span style={{ marginLeft: 10 }}>characters</span>
          </div>
          <div>
            <label><input type="checkbox" checked={maskLower} onChange={e => setMaskLower(e.target.checked)} /> Lowercase (a-z)</label>
            <label style={{ marginLeft: 15 }}><input type="checkbox" checked={maskUpper} onChange={e => setMaskUpper(e.target.checked)} /> Uppercase (A-Z)</label>
            <label style={{ marginLeft: 15 }}><input type="checkbox" checked={maskDigits} onChange={e => setMaskDigits(e.target.checked)} /> Digits (0-9)</label>
            <label style={{ marginLeft: 15 }}><input type="checkbox" checked={maskSpecial} onChange={e => setMaskSpecial(e.target.checked)} /> Special (!@#$...)</label>
          </div>
          <div style={{ marginTop: 10 }}>
            <label>Custom mask (optional): </label>
            <input type="text" value={customMask} onChange={e => setCustomMask(e.target.value)} placeholder="e.g. ?l?l?d?d" style={{ width: 250 }} />
            <small style={{ marginLeft: 10, color: 'gray' }}>Overrides auto-generated mask</small>
          </div>
          <div style={{ marginTop: 10 }}>
            <strong>Generated mask:</strong> <code>{generateMask()}</code>
          </div>
        </div>
      )}

      <button onClick={createTask} style={{ marginTop: 10 }}>Start cracking</button>

      <h2>Tasks</h2>
      {tasks.map(task => (
        <div key={task.id} style={{ border: '1px solid #ccc', margin: 10, padding: 10, borderRadius: 5, position: 'relative' }}>
          <div>Status: {task.status} {task.status === 'running' && <button onClick={() => cancelTask(task.id)} style={{ marginLeft: 10, color: 'red' }}>✖ Cancel</button>}</div>
          <div>Progress: {task.progress}%</div>
          <progress value={task.progress} max="100" style={{ width: '100%' }} />
          {task.result && <div style={{ color: 'green' }}>Password: {task.result}</div>}
          {task.error && <div style={{ color: 'red' }}>Error: {task.error}</div>}
          {task.mask && <div style={{ fontSize: 12, color: 'gray' }}>Mask: {task.mask}</div>}
          {(task.status === 'completed' || task.status === 'failed' || task.status === 'cancelled') && (
            <button onClick={() => deleteTask(task.id)} style={{ position: 'absolute', top: 10, right: 10, background: 'none', border: 'none', fontSize: 18, cursor: 'pointer' }}>🗑️</button>
          )}
        </div>
      ))}
    </div>
  );
}

export default App;