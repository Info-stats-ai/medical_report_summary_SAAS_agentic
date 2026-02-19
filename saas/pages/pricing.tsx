"use client"

import Link from 'next/link';
import { PricingTable, UserButton } from '@clerk/nextjs';

export default function Pricing() {
    return (
        <main className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
            <div className="absolute top-4 right-4 flex items-center gap-4">
                <Link
                    href="/product"
                    className="text-gray-700 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 font-medium"
                >
                    Back to App
                </Link>
                <UserButton showName={true} />
            </div>

            <div className="container mx-auto px-4 py-12">
                <header className="text-center mb-12">
                    <h1 className="text-5xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent mb-4">
                        Healthcare Professional Plan
                    </h1>
                    <p className="text-gray-600 dark:text-gray-400 text-lg max-w-2xl mx-auto">
                        Upgrade to Premium for the best AI model (GPT-5), faster responses, and priority support.
                    </p>
                </header>
                <div className="max-w-4xl mx-auto">
                    <PricingTable />
                </div>
            </div>
        </main>
    );
}
