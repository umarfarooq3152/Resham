import { useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { LogIn, LogOut, ShieldCheck, User } from 'lucide-react';
import { AuthUser } from '../api/auth';

// Shared between DiscoveryScreen and ChatSearchScreen, which previously each
// carried an identical copy of this dropdown — extracted so the size/
// department editor added here only needs to exist in one place.
const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'];
const DEPARTMENTS = ['women', 'men'] as const;

interface ProfileDropdownProps {
  authUser: AuthUser | null;
  onOpenAuth: () => void;
  onLogout: () => void;
  onUpdateProfile: (updates: Partial<Pick<AuthUser, 'preferred_size' | 'department'>>) => Promise<void>;
}

export default function ProfileDropdown({ authUser, onOpenAuth, onLogout, onUpdateProfile }: ProfileDropdownProps) {
  const [showProfile, setShowProfile] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const savePreference = async (updates: Partial<Pick<AuthUser, 'preferred_size' | 'department'>>) => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await onUpdateProfile(updates);
    } catch {
      setSaveError('Could not save — try again.');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowProfile(!showProfile)}
        className={`p-1.5 rounded-full transition-all cursor-pointer flex items-center justify-center ${showProfile ? 'bg-gray-100 text-[#003224]' : 'text-gray-500 hover:text-[#003224]'}`}
        title="My Profile"
      >
        <User className="w-4 h-4 sm:w-4.5 sm:h-4.5" />
      </button>

      <AnimatePresence>
        {showProfile && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setShowProfile(false)} />

            <motion.div
              initial={{ opacity: 0, y: 8, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.95 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
              className="absolute right-0 mt-3 w-64 bg-white border border-gray-200/60 rounded-xl shadow-xl z-50 p-4 text-left font-sans"
            >
              {authUser ? (
                <>
                  <div className="pb-3 border-b border-gray-100 mb-2">
                    <p className="text-[10px] uppercase tracking-wider text-gray-400 font-bold mb-0.5">Account</p>
                    <p className="font-serif text-sm font-bold text-gray-900 leading-snug">{authUser.name}</p>
                    <p className="text-[10px] text-gray-500 truncate mt-0.5">{authUser.email}</p>
                  </div>

                  <div className="pb-3 border-b border-gray-100 mb-2 space-y-2.5">
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-gray-400 font-bold mb-1.5">
                        Preferred Size
                      </p>
                      <div className="flex flex-wrap gap-1.5">
                        {SIZES.map((size) => (
                          <button
                            key={size}
                            onClick={() => savePreference({ preferred_size: size })}
                            disabled={isSaving}
                            className={`px-2.5 py-1 rounded-full text-[10px] font-bold transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                              authUser.preferred_size === size
                                ? 'bg-[#003224] text-white'
                                : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
                            }`}
                          >
                            {size}
                          </button>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-gray-400 font-bold mb-1.5">
                        Shopping For
                      </p>
                      <div className="flex gap-1.5">
                        {DEPARTMENTS.map((dept) => (
                          <button
                            key={dept}
                            onClick={() => savePreference({ department: dept })}
                            disabled={isSaving}
                            className={`flex-1 px-2.5 py-1 rounded-full text-[10px] font-bold capitalize transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed ${
                              authUser.department === dept
                                ? 'bg-[#003224] text-white'
                                : 'bg-gray-50 text-gray-600 hover:bg-gray-100'
                            }`}
                          >
                            {dept}
                          </button>
                        ))}
                      </div>
                    </div>
                    {saveError && <p className="text-[10px] text-red-600">{saveError}</p>}
                  </div>

                  <div className="space-y-1 text-xs">
                    <div className="flex items-center gap-2.5 py-2 px-2 rounded-lg text-gray-600">
                      <ShieldCheck className="w-4 h-4 text-emerald-700" />
                      <span>Member</span>
                    </div>
                    <div
                      onClick={() => {
                        setShowProfile(false);
                        onLogout();
                      }}
                      className="flex items-center gap-2.5 py-2 px-2 rounded-lg text-red-600 hover:bg-red-50 cursor-pointer transition-colors mt-1.5 pt-2 border-t border-gray-100"
                    >
                      <LogOut className="w-4 h-4" />
                      <span>Log Out</span>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="pb-3 border-b border-gray-100 mb-2">
                    <p className="text-[10px] uppercase tracking-wider text-gray-400 font-bold mb-0.5">Account</p>
                    <p className="text-xs text-gray-600 leading-snug">
                      Log in to save your wishlist and preferences across devices.
                    </p>
                  </div>
                  <div
                    onClick={() => {
                      setShowProfile(false);
                      onOpenAuth();
                    }}
                    className="flex items-center gap-2.5 py-2 px-2 rounded-lg text-[#003224] font-bold hover:bg-gray-50 cursor-pointer transition-colors text-xs"
                  >
                    <LogIn className="w-4 h-4" />
                    <span>Log In / Sign Up</span>
                  </div>
                </>
              )}
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
