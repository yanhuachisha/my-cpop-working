'use client';

import { Search, X } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';

interface SearchBarProps {
  placeholder?: string;
  onSearch?: (query: string) => void;
}

export function SearchBar({ placeholder = '搜索艺人或歌曲...', onSearch }: SearchBarProps) {
  const [query, setQuery] = useState('');
  const router = useRouter();

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      if (onSearch) {
        onSearch(query);
      } else {
        router.push(`/search?q=${encodeURIComponent(query)}`);
      }
    }
  };

  const clearSearch = () => {
    setQuery('');
  };

  return (
    <form className="search-bar" onSubmit={handleSearch}>
      <Search size={20} className="search-icon" />
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={placeholder}
        className="search-input"
      />
      {query && (
        <button type="button" onClick={clearSearch} className="clear-btn">
          <X size={18} />
        </button>
      )}
    </form>
  );
}
