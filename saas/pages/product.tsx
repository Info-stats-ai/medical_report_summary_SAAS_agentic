"use client"

import { useState, FormEvent } from 'react';
import { useAuth } from '@clerk/nextjs';
import DatePicker from 'react-datepicker';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import Link from 'next/link';
import { Protect, SignInButton, UserButton } from '@clerk/nextjs';

function ConsultationForm() {
    const { getToken } = useAuth();

    // Form state
    const [patientName, setPatientName] = useState('');
    const [visitDate, setVisitDate] = useState<Date | null>(new Date());
    const [notes, setNotes] = useState('');
    const [file, setFile] = useState<File | null>(null);
    const [fileError, setFileError] = useState('');

    // Streaming state
    const [output, setOutput] = useState('');
    const [loading, setLoading] = useState(false);

    // History (localStorage) — list of past summaries
    const HISTORY_KEY = 'medinotes_history';
    const MAX_HISTORY = 50;
    type HistoryEntry = { id: string; patient_name: string; date_of_visit: string; summary: string; created_at: string };
    const [history, setHistory] = useState<HistoryEntry[]>(() => {
        if (typeof window === 'undefined') return [];
        try {
            const raw = localStorage.getItem(HISTORY_KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed.slice(0, MAX_HISTORY) : [];
        } catch { return []; }
    });

    const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB
    const ACCEPT = '.pdf,image/*';

    async function fileToBase64(f: File): Promise<{ base64: string; mime: string }> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const dataUrl = reader.result as string;
                const base64 = dataUrl.split(',')[1] || '';
                resolve({ base64, mime: f.type });
            };
            reader.onerror = () => reject(reader.error);
            reader.readAsDataURL(f);
        });
    }

    async function handleSubmit(e: FormEvent) {
        e.preventDefault();
        setFileError('');
        setOutput('');
        setLoading(true);

        if (!notes.trim() && !file) {
            setOutput('Please enter consultation notes or upload a PDF/image.');
            setLoading(false);
            return;
        }
        if (file && file.size > MAX_FILE_SIZE) {
            setFileError('File must be under 5MB.');
            setLoading(false);
            return;
        }

        const jwt = await getToken();
        if (!jwt) {
            setOutput('Authentication required');
            setLoading(false);
            return;
        }

        let body: { patient_name: string; date_of_visit: string; notes?: string; file_base64?: string; file_mime?: string } = {
            patient_name: patientName,
            date_of_visit: visitDate?.toISOString().slice(0, 10) || '',
            notes: notes.trim() || undefined,
        };
        if (file) {
            const { base64, mime } = await fileToBase64(file);
            body = { ...body, file_base64: base64, file_mime: mime };
        }

        const controller = new AbortController();
        let buffer = '';

        await fetchEventSource('/api', {
            signal: controller.signal,
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${jwt}`,
            },
            body: JSON.stringify(body),
            onmessage(ev) {
                buffer += ev.data;
                setOutput(buffer);
            },
            onclose() {
                setLoading(false);
                if (buffer.trim()) {
                    const entry: HistoryEntry = {
                        id: crypto.randomUUID(),
                        patient_name: patientName,
                        date_of_visit: visitDate?.toISOString().slice(0, 10) || '',
                        summary: buffer,
                        created_at: new Date().toISOString(),
                    };
                    setHistory(prev => {
                        const next = [entry, ...prev].slice(0, MAX_HISTORY);
                        try { localStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch (_) {}
                        return next;
                    });
                }
            },
            onerror(err) {
                console.error('SSE error:', err);
                controller.abort();
                setLoading(false);
            },
        });
    }

    return (
        <div className="container mx-auto px-4 py-12 max-w-3xl">
            <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-8">
                Consultation Notes
            </h1>

            <form onSubmit={handleSubmit} className="space-y-6 bg-white dark:bg-gray-800 rounded-xl shadow-lg p-8">
                <div className="space-y-2">
                    <label htmlFor="patient" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Patient Name
                    </label>
                    <input
                        id="patient"
                        type="text"
                        required
                        value={patientName}
                        onChange={(e) => setPatientName(e.target.value)}
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
                        placeholder="Enter patient's full name"
                    />
                </div>

                <div className="space-y-2">
                    <label htmlFor="date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Date of Visit
                    </label>
                    <DatePicker
                        id="date"
                        selected={visitDate}
                        onChange={(d: Date | null) => setVisitDate(d)}
                        dateFormat="yyyy-MM-dd"
                        placeholderText="Select date"
                        required
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
                    />
                </div>

                <div className="space-y-2">
                    <label htmlFor="notes" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Consultation Notes (or upload a file below)
                    </label>
                    <textarea
                        id="notes"
                        rows={6}
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white"
                        placeholder="Enter notes, or upload a PDF or image of your report..."
                    />
                </div>

                <div className="space-y-2">
                    <label htmlFor="file" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                        Or upload PDF / image
                    </label>
                    <input
                        id="file"
                        type="file"
                        accept={ACCEPT}
                        onChange={(e) => { setFile(e.target.files?.[0] || null); setFileError(''); }}
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:text-white file:mr-4 file:py-2 file:px-4 file:rounded file:border-0 file:text-sm file:font-medium file:bg-blue-50 file:text-blue-700 dark:file:bg-blue-900/30 dark:file:text-blue-300"
                    />
                    {file && <p className="text-sm text-gray-500 dark:text-gray-400">Selected: {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}
                    {fileError && <p className="text-sm text-red-600 dark:text-red-400">{fileError}</p>}
                    <p className="text-xs text-gray-500 dark:text-gray-400">Max 5MB. PDF or image (e.g. photo of handwritten notes).</p>
                </div>

                <button 
                    type="submit" 
                    disabled={loading}
                    className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-semibold py-3 px-6 rounded-lg transition-colors duration-200"
                >
                    {loading ? 'Generating Summary...' : 'Generate Summary'}
                </button>
            </form>

            {output && (
                <section className="mt-8 bg-gray-50 dark:bg-gray-800 rounded-xl shadow-lg p-8">
                    <div className="markdown-content prose prose-blue dark:prose-invert max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>
                            {output}
                        </ReactMarkdown>
                    </div>
                </section>
            )}

            {history.length > 0 && (
                <section className="mt-10 border-t border-gray-200 dark:border-gray-700 pt-8">
                    <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">Past summaries</h2>
                    <ul className="space-y-2">
                        {history.map((entry) => (
                            <li key={entry.id}>
                                <button
                                    type="button"
                                    onClick={() => setOutput(entry.summary)}
                                    className="w-full text-left px-4 py-3 rounded-lg bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                                >
                                    <span className="font-medium text-gray-900 dark:text-gray-100">{entry.patient_name}</span>
                                    <span className="text-gray-500 dark:text-gray-400 text-sm ml-2">{entry.date_of_visit}</span>
                                    <span className="text-gray-400 dark:text-gray-500 text-xs ml-2">
                                        {new Date(entry.created_at).toLocaleString()}
                                    </span>
                                </button>
                            </li>
                        ))}
                    </ul>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">Stored in this browser. Click to view.</p>
                </section>
            )}
        </div>
    );
}

export default function Product() {
    return (
        <main className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
            {/* User Menu + Upgrade link in Top Right */}
            <div className="absolute top-4 right-4 flex items-center gap-4">
                <Link
                    href="/pricing"
                    className="text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline"
                >
                    Upgrade to Premium
                </Link>
                <UserButton showName={true} />
            </div>

            {/* Login required — no plan required; free and premium both see the app */}
            <Protect
                fallback={
                    <div className="container mx-auto px-4 py-24 text-center">
                        <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                            Sign in to use the Consultation Assistant
                        </h1>
                        <p className="text-gray-600 dark:text-gray-400 mb-8">
                            You need to be signed in to generate summaries and patient emails.
                        </p>
                        <SignInButton mode="modal">
                            <button className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-8 rounded-lg">
                                Sign in
                            </button>
                        </SignInButton>
                    </div>
                }
            >
                <ConsultationForm />
            </Protect>
        </main>
    );
}