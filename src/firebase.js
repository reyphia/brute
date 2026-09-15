import { initializeApp } from 'firebase/app';
import { getFirestore } from 'firebase/firestore';
import { getAuth } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "AIzaSyA6jPtr_F0M3HDSiPDeQgtLTV73x22yGu4",
  authDomain: "brute-me.firebaseapp.com",
  projectId: "brute-me",
  storageBucket: "brute-me.firebasestorage.app",
  messagingSenderId: "435057377710",
  appId: "1:435057377710:web:d28a7410c292b09168483f"
};

const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);
export const auth = getAuth(app);