import React from 'react';

export const metadata = {
  title: 'RoadResQ — Customer Web',
  description: 'Digital Roadside Assistance Platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif', backgroundColor: '#0f172a', color: '#f8fafc' }}>
        {children}
      </body>
    </html>
  );
}
